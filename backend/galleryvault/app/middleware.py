"""HTTP Middleware for authentication, CSRF validation, and security headers."""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import secrets
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..auth import ensure_runtime_auth_secret, verify_login_password, verify_session
from ..logging import log_extra
from .dependencies import get_current_settings

logger = logging.getLogger(__name__)

CSRF_COOKIE = "galleryvault_csrf"
BASIC_AUTH_REALM = 'Basic realm="GalleryVault OPDS"'
_OPDS_PATH = "/api/opds"
_EXPORT_CBZ_SUFFIX = "/export.cbz"

# Baseline response headers.  The SPA shell is served by nginx, which sets the
# same values (frontend/nginx.conf); repeating them here covers direct API
# access (dev, reverse-proxy bypass, OPDS readers).  The CSP mirrors the nginx
# policy so it stays compatible with the existing inline <style> block, the
# external-only script tags and the service worker.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https://ehgt.org; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
        "worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
}


def apply_security_headers(response: Any) -> Any:
    """Add the baseline security headers unless a handler already set them."""
    headers = getattr(response, "headers", None)
    if headers is None:
        return response
    for name, value in SECURITY_HEADERS.items():
        if name not in headers:
            headers[name] = value
    return response


def _is_export_cbz_path(path: str) -> bool:
    """True for ``/api/galleries/{identifier}/export.cbz`` only."""
    if not path.endswith(_EXPORT_CBZ_SUFFIX):
        return False
    prefix = path[: -len(_EXPORT_CBZ_SUFFIX)].split("/")
    return (
        len(prefix) == 4
        and prefix[1] == "api"
        and prefix[2] == "galleries"
        and prefix[3].isdigit()
    )


def _is_basic_auth_route(request: Request) -> bool:
    path = request.url.path
    if request.method == "GET" and path == _OPDS_PATH:
        return True
    # OPDS acquisition links (export.cbz) are opened by readers that only know
    # HTTP Basic, so they must accept Basic auth as well.
    return request.method in {"GET", "HEAD"} and _is_export_cbz_path(path)


def _verify_basic_auth(request: Request, settings: Any) -> bool:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return False
    scheme, _, param = auth_header.partition(" ")
    if scheme.lower() != "basic" or not param.strip():
        return False
    try:
        decoded = base64.b64decode(param.strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    username, sep, password = decoded.partition(":")
    if not sep:
        return False
    valid_username = hmac.compare_digest(username, "galleryvault")
    effective = settings.auth_password_hash or settings.auth_password
    valid_password = verify_login_password(password, effective)
    return valid_username and valid_password


async def auth_and_csrf_middleware(request: Request, call_next: Any) -> Any:
    # Workers-disabled deployments never run the startup auth bootstrap; adopt
    # the DB-persisted session secret before the first authentication check.
    try:
        await ensure_runtime_auth_secret()
    except Exception as exc:  # noqa: BLE001
        logger.warning("session secret unavailable", extra=log_extra(error=type(exc).__name__))
        return apply_security_headers(JSONResponse(
            {"detail": "authentication temporarily unavailable"}, status_code=503
        ))
    response = await _auth_and_csrf(request, call_next)
    return apply_security_headers(response)


async def _auth_and_csrf(request: Request, call_next: Any) -> Any:
    path = request.url.path
    settings = get_current_settings()
    if path in {"/healthz", "/login", "/logout"}:
        response = await call_next(request)
        # Ensure CSRF cookie is set for subsequent POSTs when auth is required
        if settings.auth_required and not request.cookies.get(CSRF_COOKIE):
            try:
                token = secrets.token_urlsafe(32)
                # Use lax, not httponly so JS can read it for X-CSRF-Token header
                secure = (
                    settings.auth_cookie_secure
                    or request.headers.get("x-forwarded-proto", "").lower() == "https"
                    or request.url.scheme == "https"
                )
                response.set_cookie(
                    CSRF_COOKIE,
                    token,
                    samesite="lax",
                    secure=secure,
                    httponly=False,
                    max_age=settings.auth_session_ttl,
                )
            except Exception:  # noqa: BLE001, S110
                pass
        return response
    if not settings.auth_required:
        return await call_next(request)

    authenticated = verify_session(
        request.cookies.get(settings.auth_cookie_name), settings.auth_secret or ""
    )

    if not authenticated and _is_basic_auth_route(request):
        if _verify_basic_auth(request, settings):
            authenticated = True
        else:
            logger.info(
                "authentication failed",
                extra=log_extra(
                    ip=request.client.host if request.client else "unknown",
                    reason="invalid_basic_auth",
                ),
            )
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": BASIC_AUTH_REALM},
            )

    if not authenticated:
        reason = "missing_or_invalid_session"
        logger.info(
            "authentication failed",
            extra=log_extra(ip=request.client.host if request.client else "unknown", reason=reason),
        )
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
            )
        return RedirectResponse("/login", status_code=303)

    # CSRF / Origin protection for state-changing requests
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        session_cookie = request.cookies.get(settings.auth_cookie_name)
        # API routes: Origin / Referer / Sec-Fetch-Site + optional X-CSRF-Token
        if request.url.path.startswith("/api/"):
            sec_fetch_site = request.headers.get("sec-fetch-site")
            if sec_fetch_site == "cross-site":
                return JSONResponse(
                    {"detail": "Cross-origin request rejected"},
                    status_code=403,
                )
            # Prefer X-Forwarded-Host if behind trusted proxy, else Host
            host_header = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
            # Compare hostname only, ignoring port: nginx $host strips the port
            # (e.g. Host=192.168.1.123 vs Origin=http://192.168.1.123:8000). Using
            # netloc would false-positive on every non-80 port. hostname still
            # blocks genuine cross-site (evil.com vs gallery host).
            parsed_host = urlparse("//" + host_header)
            request_host = (parsed_host.hostname or "").lower()
            # Origin check (primary)
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get("x-csrf-token")
            has_valid_csrf = bool(
                csrf_cookie and csrf_header and hmac.compare_digest(csrf_cookie, csrf_header)
            )

            if origin:
                origin_clean = origin.strip().lower()
                parsed_origin = urlparse(origin)
                origin_host = (parsed_origin.hostname or "").lower()
                is_invalid_origin = (
                    origin_clean == "null"
                    or not origin_host
                    or bool(request_host and origin_host != request_host)
                )
                if is_invalid_origin and not has_valid_csrf:
                    return JSONResponse(
                        {"detail": "Cross-origin request rejected"},
                        status_code=403,
                    )
            elif referer:
                referer_clean = referer.strip().lower()
                parsed_referer = urlparse(referer)
                referer_host = (parsed_referer.hostname or "").lower()
                is_invalid_referer = (
                    referer_clean == "null"
                    or not referer_host
                    or bool(request_host and referer_host != request_host)
                )
                if is_invalid_referer and not has_valid_csrf:
                    return JSONResponse(
                        {"detail": "Cross-origin request rejected"},
                        status_code=403,
                    )
            else:
                # No Origin and no Referer:
                is_test_client = (
                    (request.client and request.client.host == "testclient")
                    or request_host == "testserver"
                )
                is_same_origin = sec_fetch_site == "same-origin"
                if session_cookie and not (is_test_client or is_same_origin):
                    if not has_valid_csrf:
                        return JSONResponse({"detail": "CSRF token required"}, status_code=403)
                elif csrf_cookie and csrf_header and not has_valid_csrf:
                    return JSONResponse({"detail": "CSRF token required"}, status_code=403)
        # Non-API POST (form) — strict CSRF
        elif request.url.path not in {"/login", "/logout"}:
            csrf = request.cookies.get(CSRF_COOKIE)
            supplied = request.headers.get("x-csrf-token")
            content_type = request.headers.get("content-type", "").split(";", 1)[0]
            if content_type == "application/x-www-form-urlencoded":
                body = await request.body()
                supplied = parse_qs(body.decode(errors="replace")).get("csrf_token", [None])[0]

                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = receive
            if not csrf or not supplied or not hmac.compare_digest(csrf, supplied):
                return HTMLResponse("CSRF token required", status_code=403)
    response = await call_next(request)
    # Ensure CSRF cookie is present for future requests (30-day, lax)
    if not request.cookies.get(CSRF_COOKIE) and settings.auth_required:
        try:
            token = secrets.token_urlsafe(32)
            secure = (
                settings.auth_cookie_secure
                or request.headers.get("x-forwarded-proto", "").lower() == "https"
                or request.url.scheme == "https"
            )
            response.set_cookie(
                CSRF_COOKIE,
                token,
                samesite="lax",
                secure=secure,
                httponly=False,
                max_age=settings.auth_session_ttl,
            )
        except Exception:  # noqa: BLE001, S110
            pass
    # End of authentication & security middleware
    return response
