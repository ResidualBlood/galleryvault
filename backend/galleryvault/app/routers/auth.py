"""Authentication and onboarding endpoints."""

from __future__ import annotations

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

from galleryvault.app import main
from galleryvault.auth import create_session, hash_password
from galleryvault.db.models import Gallery
from galleryvault.db.repository import SettingsRepository
from galleryvault.logging import log_extra
from galleryvault.secrets import encrypt, encryption_enabled

router = APIRouter()


class ChangePasswordRequest(BaseModel):
    current: str = ""
    new: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def login(request: Request):
    ip = main._client_ip(request)
    if not await main._login_gate(ip):
        main.logger.info(
            "login rate limited", extra=log_extra(ip=ip, reason="rate_limit")
        )
        return HTMLResponse("Too many attempts, try again later", status_code=429)
    form = parse_qs((await request.body()).decode(errors="replace"), keep_blank_values=True)
    password = form.get("password", [""])[0]
    valid = True
    if main._settings().auth_required:
        valid = main.verify_login_password(password, main._password_effective())
    if not valid:
        main.logger.info(
            "authentication failed",
            extra=log_extra(
                ip=ip, reason="invalid_password"
            ),
        )
        return RedirectResponse("/login?error=1", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        main._settings().auth_cookie_name,
        create_session(main._settings().auth_secret or "", main._settings().auth_session_ttl),
        httponly=True,
        samesite="lax",
        secure=main._settings().auth_cookie_secure,
        max_age=main._settings().auth_session_ttl,
    )
    await main._login_succeeded(ip)
    return response


@router.get("/login")
async def login_get() -> RedirectResponse:
    """The frontend is served separately; a GET to /login just redirects to the
    SPA root (hash-routed), keeping e.g. /login?error=1 on the frontend."""
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(main._settings().auth_cookie_name)
    return response


@router.get("/api/auth/session")
async def auth_session() -> dict[str, object]:
    return {
        "authenticated": True,
        "auth_required": main._settings().auth_required,
        "must_change_password": main._must_change_password(),
    }


@router.get("/api/onboarding/status")
async def onboarding_status() -> dict[str, object]:
    """Setup progress used by the first-run wizard (password, ExHentai, library)."""
    settings = main._settings()
    password_default = settings.auth_required and not (
        settings.auth_password_hash or settings.auth_password
    )
    exhentai_configured = bool(settings.exhentai_cookies)
    library_count = 0
    try:
        async with main._settings_session() as session:
            library_count = int(
                await session.scalar(select(func.count()).select_from(Gallery)) or 0
            )
    except Exception as exc:  # noqa: BLE001 - DB down: fall back to a 0 count
        main.logger.warning("onboarding status could not read library count", extra={"error": str(exc)})
    return {
        "password_default": password_default,
        "exhentai_configured": exhentai_configured,
        "library_count": library_count,
    }


@router.post("/api/auth/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest) -> None:
    effective = main._password_effective()
    using_default = effective is None
    current_valid = (
        using_default and body.current == main.DEFAULT_PASSWORD
    ) or main.verify_login_password(body.current, effective)
    if not current_valid:
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if body.new == main.DEFAULT_PASSWORD and using_default:
        raise HTTPException(status_code=422, detail="New password cannot be the default")
    new_hash = hash_password(body.new)
    # Rotate auth_secret so every previously issued session cookie is revoked.
    new_secret = _secrets.token_urlsafe(32)
    stored = {"auth_password_hash": new_hash, "auth_secret": new_secret}
    if encryption_enabled():
        stored = {k: encrypt(v) for k, v in stored.items()}
    try:
        async with main._settings_session() as session, session.begin():
            await SettingsRepository(session).save_extra(stored)
    except SQLAlchemyError as exc:
        raise main._db_error(exc) from exc
    main.app.state.settings = main.app.state.settings.model_copy(
        update={"auth_secret": new_secret, "auth_password_hash": new_hash}
    )
    # Hand the current user a fresh cookie signed with the new secret so their
    # own password change does not log them out while everyone else's old
    # sessions are revoked immediately.
    response = Response(status_code=204)
    response.set_cookie(
        main._settings().auth_cookie_name,
        create_session(new_secret, main._settings().auth_session_ttl),
        httponly=True,
        samesite="lax",
        secure=main._settings().auth_cookie_secure,
        max_age=main._settings().auth_session_ttl,
    )
    main.logger.info("account password changed")
    return response
