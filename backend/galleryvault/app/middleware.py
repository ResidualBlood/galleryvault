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

from ..auth import verify_login_password, verify_session
from ..logging import log_extra
from .dependencies import get_current_settings

logger = logging.getLogger(__name__)

CSRF_COOKIE = "galleryvault_csrf"
BASIC_AUTH_REALM = 'Basic realm="GalleryVault OPDS"'


def _is_basic_auth_route(request: Request) -> bool:
    if request.method != "GET":
        return False
    path = request.url.path
    if path == "/api/opds":
        return True
    if path.startswith("/api/galleries/") and path.endswith("/export.cbz"):
        parts = path.split("/")
        return len(parts) == 5 and bool(parts[3])
    return False


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
    path = request.url.path
    settings = get_current_settings()
    if path in {"/healthz", "/metrics", "/login", "/logout"}:
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
                    max_age=86400 * 30,
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
            if origin:
                parsed_origin = urlparse(origin)
                origin_host = (parsed_origin.hostname or "").lower()
                if origin_host and request_host and origin_host != request_host:
                    return JSONResponse(
                        {"detail": "Cross-origin request rejected"},
                        status_code=403,
                    )
            elif referer:
                parsed_referer = urlparse(referer)
                referer_host = (parsed_referer.hostname or "").lower()
                if referer_host and request_host and referer_host != request_host:
                    return JSONResponse(
                        {"detail": "Cross-origin request rejected"},
                        status_code=403,
                    )
            else:
                # No Origin/Referer: fall back to CSRF token validation if both present
                # Old browsers or curl without Origin would otherwise bypass.
                if csrf_cookie and csrf_header and not hmac.compare_digest(csrf_cookie, csrf_header):
                    return JSONResponse({"detail": "CSRF token required"}, status_code=403)
                # If no CSRF cookie yet, allow (will be set on response below) — same-origin fetch without Origin is normal
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
                max_age=86400 * 30,
            )
        except Exception:  # noqa: BLE001, S110
            pass
    return response
