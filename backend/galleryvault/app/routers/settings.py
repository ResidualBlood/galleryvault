"""Settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from galleryvault.app import main
from galleryvault.db.repository import FavoritesRepository, GalleryRepository, SettingsRepository

router = APIRouter()


@router.get("/api/settings")
async def settings_get() -> dict[str, object]:
    try:
        async with main._settings_session() as session:
            persisted = await SettingsRepository(session).get()
        persisted = main._decrypt_user_settings(persisted)
        main._update_runtime_settings(persisted)
    except Exception as exc:  # noqa: BLE001 - DB down: serve in-memory settings
        # DB unavailable: serve the current in-memory settings unchanged.
        main.logger.warning("settings could not be re-read", extra={"error": str(exc)})
    return main._settings_public()


@router.post("/api/settings")
async def settings_save(body: main.SettingsRequest) -> dict[str, object]:
    return await _save_settings(body)


@router.post("/api/settings/exhentai/test")
async def settings_test_exhentai() -> dict[str, str]:
    if not main._settings().exhentai_cookies:
        return {"status": "not_configured", "message": "ExHentai Cookie 未设置"}
    try:
        response = await main.app.state.eh_client._get("/")
        return {"status": "ok", "message": f"HTTP {response.status_code}"}
    except Exception:  # noqa: BLE001
        return {"status": "failed", "message": "ExHentai 登录测试失败"}


async def _save_settings(body: main.SettingsRequest) -> dict[str, object]:
    _settings = main._settings
    _settings_session = main._settings_session
    _settings_public = main._settings_public
    _update_runtime_settings = main._update_runtime_settings
    _refresh_services = main._refresh_services
    _db_error = main._db_error
    values = body.model_dump(exclude_none=True)
    # A blank bot token must never clobber a configured one (older frontends /
    # cached JS used to submit an empty value). "Leave blank to keep" semantics.
    if "telegram_bot_token" in values and not str(values["telegram_bot_token"]).strip():
        values.pop("telegram_bot_token", None)
    if values.get("exhentai_base_url"):
        from urllib.parse import urlparse as _base_parse

        host = (_base_parse(str(values["exhentai_base_url"])).hostname or "").lower()
        if host not in {"exhentai.org", "e-hentai.org"} and not host.endswith(
            (".exhentai.org", ".e-hentai.org")
        ):
            raise HTTPException(
                status_code=422, detail="exhentai_base_url must be on exhentai.org / e-hentai.org"
            )
    if "library_roots" in values:
        values["library_roots"] = main.normalize_library_roots(values["library_roots"])
    # An empty input means "clear this proxy"; an empty string would be sent to
    # httpx verbatim and crash every outbound request.
    for proxy_key in ("http_proxy", "socks5_proxy"):
        if values.get(proxy_key) == "":
            values[proxy_key] = None
    if "favorites" in values:
        favorites = values.pop("favorites")

        def _favcat(item: dict[str, object]) -> int:
            try:
                return int(item.get("favcat", -1))
            except (TypeError, ValueError):
                return -1

        if not isinstance(favorites, list) or any(
            not isinstance(item, dict)
            or _favcat(item) not in range(10)
            or item.get("mode") not in {"monitor_only", "incremental", "force"}
            for item in favorites
        ):
            raise HTTPException(status_code=422, detail="invalid favorites configuration")
        values["favorites_categories"] = [
            _favcat(item) for item in favorites if bool(item.get("enabled", True))
        ]
    else:
        favorites = []
    if "exhentai_cookies" in values:
        values["exhentai_cookies"] = {
            str(key): str(value)
            for key, value in values["exhentai_cookies"].items()
            if str(key) in {"ipb_member_id", "ipb_pass_hash", "igneous"} and str(value)
        }
    cookie_fields = {}
    for key in ("ipb_member_id", "ipb_pass_hash", "igneous"):
        value = values.pop(key, None)
        if value:
            cookie_fields[key] = value
    if cookie_fields:
        values["exhentai_cookies"] = {**_settings().exhentai_cookies, **cookie_fields}
    _update_runtime_settings(values)
    # Start from what is already persisted so a field the frontend did not
    # submit (e.g. the bot token, which is never echoed and only sent when
    # changed) is kept. save() replaces the whole dict, so this DB-read + merge
    # is what protects the token from being dropped by an unrelated save.
    try:
        async with _settings_session() as session:
            db_settings = await SettingsRepository(session).get()
    except Exception:  # noqa: BLE001 - DB down: fall back to in-memory settings
        db_settings = {}
    persisted_values = {**db_settings, **values}
    # Encrypt sensitive values for at-rest storage; values that are already
    # stored encrypted (e.g. an unchanged bot token read from the DB) pass
    # through untouched.
    cookies = persisted_values.get("exhentai_cookies")
    if isinstance(cookies, (dict, list)) and cookies:
        persisted_values["exhentai_cookies"] = main.encrypt_json(cookies)
    token = persisted_values.get("telegram_bot_token")
    if isinstance(token, str) and token and not main.is_encrypted(token):
        persisted_values["telegram_bot_token"] = main.encrypt(token)
    # All user-editable settings live in the DB (single source of truth).
    try:
        async with _settings_session() as session, session.begin():
            await SettingsRepository(session).save(persisted_values)
            for item in favorites:
                favcat = _favcat(item)
                row = await FavoritesRepository(session).category(favcat)
                if row is None:
                    from galleryvault.db.models import FavoritesMonitor

                    row = FavoritesMonitor(favcat=favcat)
                    session.add(row)
                row.enabled = bool(item.get("enabled", True))
                row.mode = str(item["mode"])
                row.poll_interval_seconds = max(
                    60, int(item.get("poll_interval_minutes", 720)) * 60
                )
    except Exception as exc:
        raise _db_error(exc) from exc
    # Switching the base URL from the public E-Hentai mirror back to ExHentai
    # restores tag sync for galleries that were suspended as "not visible"
    # (an ExHentai-only gallery 404s on e-hentai.org). Resume them so the tag
    # worker picks them up without manual action.
    old_base = str(db_settings.get("exhentai_base_url") or "")
    new_base = str(persisted_values.get("exhentai_base_url") or "")
    if main._is_public_site(old_base) and not main._is_public_site(new_base):
        try:
            async with _settings_session() as session, session.begin():
                resumed = await GalleryRepository(session).resume_not_visible()
            if resumed:
                main.logger.info(
                    "resumed tag sync for not-visible galleries", extra={"count": resumed}
                )
        except Exception as exc:  # noqa: BLE001 - best-effort
            main.logger.warning(
                "could not resume not-visible galleries", extra={"error": str(exc)}
            )
    await _refresh_services()
    return _settings_public()
