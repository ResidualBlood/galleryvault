"""Authentication and onboarding endpoints."""

from __future__ import annotations

import logging
import secrets as _secrets
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from ...auth import (
    DEFAULT_PASSWORD,
    client_ip,
    create_session,
    hash_password,
    login_gate,
    login_succeeded,
    verify_login_password,
)
from ...db.models import Gallery
from ...db.repository import SettingsRepository
from ...logging import log_extra
from ...secrets import encrypt, encryption_enabled
from ..dependencies import db_error, get_current_settings, get_session
from ..state import app_state

logger = logging.getLogger(__name__)
router = APIRouter()


class ChangePasswordRequest(BaseModel):
    current: str = ""
    new: str = Field(min_length=1, max_length=256)


def _password_effective() -> str | None:
    settings = get_current_settings()
    if settings.auth_password_hash:
        return settings.auth_password_hash
    if settings.auth_password:
        return settings.auth_password
    return None


def _must_change_password() -> bool:
    settings = get_current_settings()
    auth_hash_configured = bool(settings.auth_password_hash or settings.auth_password)
    return bool(settings.auth_required and (not auth_hash_configured or settings.auth_password == DEFAULT_PASSWORD))


@router.post("/login")
async def login(request: Request):
    ip = client_ip(request)
    if not await login_gate(ip):
        logger.info(
            "login rate limited", extra=log_extra(ip=ip, reason="rate_limit")
        )
        return HTMLResponse("Too many attempts, try again later", status_code=429)
    form = parse_qs((await request.body()).decode(errors="replace"), keep_blank_values=True)
    password = form.get("password", [""])[0]
    if len(password) > 256:
        password = password[:256]
    valid = True
    settings = get_current_settings()
    if settings.auth_required:
        valid = verify_login_password(password, _password_effective())
    if not valid:
        logger.info(
            "authentication failed",
            extra=log_extra(ip=ip, reason="invalid_password"),
        )
        return RedirectResponse("/login?error=1", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        settings.auth_cookie_name,
        create_session(settings.auth_secret or "", settings.auth_session_ttl),
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=settings.auth_session_ttl,
    )
    await login_succeeded(ip)
    return response


@router.get("/login")
async def login_get() -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout():
    settings = get_current_settings()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.auth_cookie_name)
    return response


@router.get("/api/auth/session")
async def auth_session() -> dict[str, object]:
    settings = get_current_settings()
    return {
        "authenticated": True,
        "auth_required": settings.auth_required,
        "must_change_password": _must_change_password(),
    }


@router.get("/api/onboarding/status")
async def onboarding_status() -> dict[str, object]:
    settings = get_current_settings()
    password_default = settings.auth_required and not (
        settings.auth_password_hash or settings.auth_password
    )
    exhentai_configured = bool(settings.exhentai_cookies)
    library_count = 0
    try:
        async for session in get_session():
            library_count = int(
                await session.scalar(select(func.count()).select_from(Gallery)) or 0
            )
            break
    except Exception as exc:  # noqa: BLE001
        logger.warning("onboarding status could not read library count", extra={"error": str(exc)})
    return {
        "password_default": password_default,
        "exhentai_configured": exhentai_configured,
        "library_count": library_count,
    }


@router.post("/api/auth/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest) -> Response:
    effective = _password_effective()
    using_default = effective is None
    current_valid = (
        using_default and body.current == DEFAULT_PASSWORD
    ) or verify_login_password(body.current, effective)
    if not current_valid:
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if body.new == DEFAULT_PASSWORD and using_default:
        raise HTTPException(status_code=422, detail="New password cannot be the default")
    new_hash = hash_password(body.new)
    new_secret = _secrets.token_urlsafe(32)
    stored = {"auth_password_hash": new_hash, "auth_secret": new_secret}
    if encryption_enabled():
        stored = {k: encrypt(v) for k, v in stored.items()}
    try:
        async for session in get_session():
            async with session.begin():
                await SettingsRepository(session).save_extra(stored)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc

    current_settings = get_current_settings()
    app_state.settings = current_settings.model_copy(
        update={"auth_secret": new_secret, "auth_password_hash": new_hash}
    )
    response = Response(status_code=204)
    response.set_cookie(
        current_settings.auth_cookie_name,
        create_session(new_secret, current_settings.auth_session_ttl),
        httponly=True,
        samesite="lax",
        secure=current_settings.auth_cookie_secure,
        max_age=current_settings.auth_session_ttl,
    )
    logger.info("account password changed")
    return response
