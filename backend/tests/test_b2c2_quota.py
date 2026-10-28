"""B2-C2: ``/api/quota`` must not echo exception text to clients.

Review 03 #19: ``get_quota`` returned ``type(exc).__name__ + ": " + str(exc)``
in the JSON body. Exception strings can embed cookies, tokens or internal
paths, so the endpoint now answers with a generic message and logs the details
(masked) instead.
"""

from __future__ import annotations

import logging

import pytest

from galleryvault.app.state import app_state
from galleryvault.config import get_settings

_LEAKY_ERROR = "RuntimeError: cookie=ipb_member_id=42&secret=topsecret at /srv/private"


def _patch_quota_dependencies(client: object) -> None:
    app_state.extra["gp_cache"] = {}
    app_state.eh_client = client
    app_state.settings = get_settings()


@pytest.fixture(autouse=True)
def _clean_quota_state():
    saved_client = app_state.eh_client
    saved_cache = app_state.extra.get("gp_cache")
    try:
        yield
    finally:
        app_state.eh_client = saved_client
        if saved_cache is None:
            app_state.extra.pop("gp_cache", None)
        else:
            app_state.extra["gp_cache"] = saved_cache


@pytest.mark.asyncio
async def test_quota_failure_returns_generic_error_and_logs_details(caplog) -> None:
    from galleryvault.app.routers import tasks as tasks_mod

    class FailingClient:
        async def fetch_gp_balance(self) -> int:
            raise RuntimeError(_LEAKY_ERROR)

        async def fetch_image_limits(self) -> None:
            return None

    _patch_quota_dependencies(FailingClient())

    with caplog.at_level(logging.WARNING, logger="galleryvault.app.routers.tasks"):
        result = await tasks_mod.get_quota()

    assert result["error"] == "quota check failed"
    assert "RuntimeError" not in result["error"]
    assert "topsecret" not in str(result)
    assert "/srv/private" not in str(result)

    logged = [
        record.context.get("detail", "")
        for record in caplog.records
        if record.name == "galleryvault.app.routers.tasks"
        and record.getMessage() == "quota check failed"
    ]
    assert logged, "quota failure must be logged"
    # Details reach the log, with credential-looking values masked.
    assert any("/srv/private" in detail for detail in logged)
    assert any("***" in detail for detail in logged)
    assert all("topsecret" not in detail for detail in logged)
    assert any(
        record.context.get("error") == "RuntimeError"
        for record in caplog.records
        if record.name == "galleryvault.app.routers.tasks"
    )


@pytest.mark.asyncio
async def test_quota_cached_failure_keeps_generic_error(caplog) -> None:
    from galleryvault.app.routers import tasks as tasks_mod

    class FailingClient:
        async def fetch_gp_balance(self) -> int:
            raise ValueError(_LEAKY_ERROR)

        async def fetch_image_limits(self) -> None:
            return None

    _patch_quota_dependencies(FailingClient())

    with caplog.at_level(logging.WARNING, logger="galleryvault.app.routers.tasks"):
        first = await tasks_mod.get_quota()
        second = await tasks_mod.get_quota()

    assert first["error"] == second["error"] == "quota check failed"
    cached = app_state.extra["gp_cache"]
    assert cached["error"] == "quota check failed"
    assert "topsecret" not in str(cached)
