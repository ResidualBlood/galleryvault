"""Regression tests for favorites/remove cloud-failure reporting.

EhClient.remove_favorites previously sent every gid in one POST and raised on
any non-2xx, so a partial cloud failure left no trace of which gids failed.
It now chunks (25/batch), degrades a failed chunk to per-gid retries, and
returns the list of gids that could not be removed.  favorites_remove passes
those into the Logs entry (reason + failed status) and the API response.
"""

import httpx
import pytest

from galleryvault.config import Settings
from galleryvault.services.eh_client import EhClient, EhClientError


def _handler(*, fail_gids=(), bad_batch=()):
    """Build a MockTransport handler that drops specific gids.

    ``fail_gids``: gids whose individual POST returns 500.  ``bad_batch``:
    first batch of up to 25 gids that gets a 500 (triggers per-gid retry).
    """
    requests: list[tuple[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        parsed = parse_qs(request.content.decode(errors="replace"))
        modify = [v for v in parsed.get("modifygids[]", [])]
        requests.append((request.method, modify))
        if any(g in bad_batch for g in [int(g) for g in modify]):
            return httpx.Response(500, text="boom")
        if any(int(g) in fail_gids for g in modify):
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text="ok")

    return handler, requests


async def test_remove_favorites_chunks_over_25() -> None:
    handler, requests = _handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.remove_favorites(list(range(1, 60)))

    assert failed == []
    # 59 gids -> 3 chunks (25/25/9).
    assert len(requests) == 3
    assert [len(r[1]) for r in requests] == [25, 25, 9]
    assert all(g in r[1] for r in requests for g in r[1])


async def test_remove_favorites_returns_failed_gids() -> None:
    handler, requests = _handler(fail_gids={7})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.remove_favorites([1, 7, 9])

    assert failed == [7]
    assert len(requests) == 4  # one failed batch + per-gid retries
    assert requests[0][1] == ["1", "7", "9"]
    # The retry re-sent the failed batch per-gid.
    assert [g for _, batch in requests[1:] for g in batch] == ["1", "7", "9"]


async def test_remove_favorites_bad_batch_degrades_to_per_gid() -> None:
    handler, requests = _handler(bad_batch=(1, 7, 9))
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.remove_favorites([1, 7, 9])

    # The whole batch failed once, then each gid retried individually; only the
    # gid whose individual POST also fails surfaces.
    assert failed == [1, 7, 9]
    assert requests[0][1] == ["1", "7", "9"]
    assert [r[1][0] for r in requests[1:]] == ["1", "7", "9"]


async def test_remove_favorites_empty_is_noop() -> None:
    handler, requests = _handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        assert await client.remove_favorites([]) == []
    assert requests == []


async def test_remove_favorites_auth_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="login required")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        with pytest.raises(EhClientError):
            await client.remove_favorites([1])


def test_record_favorites_remove_log_appends_cloud_failures(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_remove_log
    from galleryvault.app.state import app_state

    entries: list[dict[str, object]] = []

    def record(kind, start, end, status, *, reason="", done=0, total=0):
        entries.append(
            {"kind": kind, "status": status, "reason": reason, "done": done, "total": total}
        )

    monkeypatch.setattr(app_state.task_manager, "record_task", record)

    _record_favorites_remove_log([1, 2, 3], 2, [], [3])

    assert entries[0]["kind"] == "favorites-remove"
    assert entries[0]["status"] == "failed"
    assert "cloud remove failed 1: 3" in entries[0]["reason"]
    assert entries[0]["total"] == 3


def test_record_favorites_remove_log_success_when_cloud_ok(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_remove_log
    from galleryvault.app.state import app_state

    entries: list[dict[str, object]] = []

    def record(kind, start, end, status, *, reason="", done=0, total=0):
        entries.append({"status": status, "reason": reason})

    monkeypatch.setattr(app_state.task_manager, "record_task", record)

    _record_favorites_remove_log([1, 2, 3], 3, [], [])

    assert entries[0]["status"] == "success"
    assert "cloud remove failed" not in entries[0]["reason"]


def test_record_favorites_remove_log_truncates_long_failure_list(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_remove_log
    from galleryvault.app.state import app_state

    entries: list[str] = []

    def record(kind, start, end, status, *, reason="", done=0, total=0):
        entries.append(reason)

    monkeypatch.setattr(app_state.task_manager, "record_task", record)

    _record_favorites_remove_log([], 0, [], list(range(1, 20)))

    assert "cloud remove failed 19: 1, 2, 3, 4, 5" in entries[0]
    assert "(+14 more)" in entries[0]
