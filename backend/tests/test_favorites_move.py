"""Tests for favorites/move endpoint and EhClient.move_favorites."""

import httpx
import pytest
from pydantic import ValidationError

from galleryvault.config import Settings
from galleryvault.services.eh_client import EhClient, EhClientError


def _handler(*, fail_gids=(), bad_batch=()):
    requests: list[tuple[str, str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        parsed = parse_qs(request.content.decode(errors="replace"))
        modify = [v for v in parsed.get("modifygids[]", [])]
        ddact = parsed.get("ddact", [""])[0]
        requests.append((request.method, ddact, modify))
        if any(g in bad_batch for g in [int(g) for g in modify]):
            return httpx.Response(500, text="boom")
        if any(int(g) in fail_gids for g in modify):
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text="ok")

    return handler, requests


async def test_move_favorites_sends_correct_payload() -> None:
    handler, requests = _handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites([10, 20], target_favcat=3)

    assert failed == []
    assert len(requests) == 1
    method, ddact, modify = requests[0]
    assert method == "POST"
    assert ddact == "fav3"
    assert modify == ["10", "20"]


async def test_move_favorites_chunks_over_25() -> None:
    handler, requests = _handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites(list(range(1, 60)), target_favcat=5)

    assert failed == []
    assert len(requests) == 3
    assert [len(r[2]) for r in requests] == [25, 25, 9]
    assert all(r[1] == "fav5" for r in requests)


async def test_move_favorites_returns_failed_gids() -> None:
    handler, requests = _handler(fail_gids={7})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites([1, 7, 9], target_favcat=2)

    assert failed == [7]
    assert len(requests) == 4  # one failed batch + per-gid retries


async def test_move_favorites_bad_batch_degrades_to_per_gid() -> None:
    handler, _requests = _handler(bad_batch=(1, 7, 9))
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.move_favorites([1, 7, 9], target_favcat=1)

    assert failed == [1, 7, 9]


async def test_move_favorites_empty_is_noop() -> None:
    handler, requests = _handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        assert await client.move_favorites([], target_favcat=0) == []
    assert requests == []


async def test_move_favorites_invalid_favcat_raises() -> None:
    client = EhClient(Settings(exhentai_base_url="https://exhentai.org"))
    with pytest.raises(ValueError):
        await client.move_favorites([1], target_favcat=-1)
    with pytest.raises(ValueError):
        await client.move_favorites([1], target_favcat=10)


async def test_move_favorites_auth_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="login required")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        with pytest.raises(EhClientError):
            await client.move_favorites([1], target_favcat=2)


def test_favorites_move_request_schema() -> None:
    from galleryvault.app.schemas import FavoritesMoveRequest

    # Direct gids
    req = FavoritesMoveRequest(gids=[1, 2, 3], target_favcat=4)
    assert req.gids == [1, 2, 3]
    assert req.target_favcat == 4

    # items fallback
    req2 = FavoritesMoveRequest(items=[{"gid": "123"}, {"gid": 456}], target_favcat=0)
    assert req2.gids == [123, 456]
    assert req2.target_favcat == 0

    # Validation errors
    with pytest.raises(ValidationError):
        FavoritesMoveRequest(gids=[1], target_favcat=-1)
    with pytest.raises(ValidationError):
        FavoritesMoveRequest(gids=[1], target_favcat=10)


@pytest.mark.asyncio
async def test_favorites_move_endpoint_happy_path(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import favorites_move
    from galleryvault.app.schemas import FavoritesMoveRequest
    from galleryvault.app.state import app_state

    class DummyClient:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            assert target_favcat == 3
            return []

    class DummyRepo:
        def __init__(self, session):
            pass

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            assert target_favcat == 3
            return len(gids)

    class DummySession:
        def begin(self):
            class DummyCtx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return DummyCtx()

    async def dummy_get_session():
        yield DummySession()

    monkeypatch.setattr(app_state, "eh_client", DummyClient())
    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    res = await favorites_move(FavoritesMoveRequest(gids=[100, 200], target_favcat=3))
    assert res["cloud_ok"] is True
    assert res["cloud_moved"] == 2
    assert res["cloud_failed"] == []
    assert res["local_moved"] == 2
    assert res["target_favcat"] == 3


@pytest.mark.asyncio
async def test_favorites_move_endpoint_partial_cloud_failure(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import favorites_move
    from galleryvault.app.schemas import FavoritesMoveRequest
    from galleryvault.app.state import app_state

    moved_locally: list[int] = []

    class DummyClient:
        async def move_favorites(self, gids: list[int], target_favcat: int) -> list[int]:
            # gid 200 fails in cloud
            return [200]

    class DummyRepo:
        def __init__(self, session):
            pass

        async def move_gids(self, gids: list[int], target_favcat: int) -> int:
            moved_locally.extend(gids)
            return len(gids)

    class DummySession:
        def begin(self):
            class DummyCtx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return DummyCtx()

    async def dummy_get_session():
        yield DummySession()

    monkeypatch.setattr(app_state, "eh_client", DummyClient())
    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    res = await favorites_move(FavoritesMoveRequest(gids=[100, 200], target_favcat=3))
    assert res["cloud_ok"] is False
    assert res["cloud_moved"] == 1
    assert res["cloud_failed"] == [200]
    assert res["local_moved"] == 1
    # Only gid 100 was moved locally, 200 was skipped
    assert moved_locally == [100]


def test_record_favorites_move_log(monkeypatch) -> None:
    from galleryvault.app import main
    from galleryvault.app.routers.favorites import _record_favorites_move_log

    entries: list[dict[str, object]] = []

    def record(kind, start, end, status, *, reason="", done=0, total=0):
        entries.append(
            {"kind": kind, "status": status, "reason": reason, "done": done, "total": total}
        )

    monkeypatch.setattr(main, "_record_task", record)

    # Success case
    _record_favorites_move_log([1, 2], 3, [], 2)
    assert entries[0]["kind"] == "favorites-move"
    assert entries[0]["status"] == "success"
    assert entries[0]["reason"] == "moved 2 to #3"
    assert entries[0]["done"] == 2
    assert entries[0]["total"] == 2

    # Partial failure case
    _record_favorites_move_log([1, 2, 3], 4, [3], 2)
    assert entries[1]["status"] == "failed"
    assert "moved 2 to #4" in entries[1]["reason"]
    assert "cloud move failed 1: 3" in entries[1]["reason"]


