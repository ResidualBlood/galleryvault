"""Tests for favorites/add endpoint and EhClient.add_favorite / add_favorites."""

from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from galleryvault.app.schemas import FavoritesAddRequest
from galleryvault.config import Settings
from galleryvault.services.eh_client import EhClient, EhClientError


def _add_handler(*, fail_gids=(), auth_fail: bool = False):
    requests: list[tuple[str, str, dict[str, list[str]]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        parsed = parse_qs(request.content.decode(errors="replace"))
        url_path = str(request.url)
        requests.append((request.method, url_path, parsed))

        if auth_fail:
            return httpx.Response(401, text="Must be logged in")

        # Check gid from url
        import re

        match = re.search(r"gid=(\d+)", url_path)
        gid = int(match.group(1)) if match else None
        if gid and gid in fail_gids:
            return httpx.Response(500, text="cloud error")
        return httpx.Response(200, text="<html><body>Updated</body></html>")

    return handler, requests


async def test_add_favorite_sends_correct_payload() -> None:
    handler, requests = _add_handler()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        await client.add_favorite(12345, "abcdef", 3, note="test note")

    assert len(requests) == 1
    method, url, form = requests[0]
    assert method == "POST"
    assert "gid=12345" in url
    assert "t=abcdef" in url
    assert "act=addfav" in url
    assert form["favcat"] == ["3"]
    assert form["favnote"] == ["test note"]
    assert form["update"] == ["1"]
    assert form["submit"] == ["Apply Changes"]


async def test_add_favorites_batch_returns_failed_gids() -> None:
    handler, requests = _add_handler(fail_gids={200})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.add_favorites(
            [(100, "tok1"), (200, "tok2"), (300, "tok3")], favcat=2
        )

    assert failed == [200]
    assert len(requests) == 3


async def test_add_favorites_auth_keeps_prior_successes() -> None:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import re

        match = re.search(r"gid=(\d+)", str(request.url))
        gid = int(match.group(1)) if match else 0
        seen.append(gid)
        if gid == 100:
            return httpx.Response(200, text="<html><body>Updated</body></html>")
        return httpx.Response(401, text="Must be logged in")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.add_favorites(
            [(100, "tok1"), (200, "tok2"), (300, "tok3")], favcat=2
        )
    assert failed == [200, 300]
    assert seen == [100, 200]


async def test_add_favorites_mid_loop_abort_keeps_successes() -> None:
    seen: list[int] = []

    class BoomItems(list):
        def __iter__(self):
            for i, item in enumerate(list.__iter__(self)):
                if i == 1:
                    raise RuntimeError("loop boom")
                yield item

    def handler(request: httpx.Request) -> httpx.Response:
        import re

        match = re.search(r"gid=(\d+)", str(request.url))
        gid = int(match.group(1)) if match else 0
        seen.append(gid)
        return httpx.Response(200, text="<html><body>Updated</body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        failed = await client.add_favorites(
            BoomItems([(100, "tok1"), (200, "tok2"), (300, "tok3")]), favcat=2
        )
    assert failed == [200, 300]
    assert 100 not in failed
    assert seen == [100]


async def test_add_favorite_auth_failure_raises() -> None:
    handler, _ = _add_handler(auth_fail=True)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://exhentai.org", transport=transport
    ) as http_client:
        client = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=http_client)
        with pytest.raises(EhClientError):
            await client.add_favorite(100, "tok", 1)


def test_favorites_add_request_schema() -> None:
    req = FavoritesAddRequest(gid=123, token="abc", target_favcat=4, note="hello")
    assert req.items == [{"gid": 123, "token": "abc", "note": "hello"}]

    req_multi = FavoritesAddRequest(
        target_favcat=5,
        items=[{"gid": 1, "token": "t1"}, {"gid": 2, "token": "t2"}],
    )
    assert len(req_multi.items) == 2

    with pytest.raises(ValidationError):
        FavoritesAddRequest(target_favcat=10)


async def test_favorites_add_endpoint_happy_path(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import favorites_add

    class DummyClient:
        async def add_favorites(self, pairs, target_favcat, note=""):
            return []

    remembered = []

    class DummyRepo:
        def __init__(self, session):
            self.session = session

        async def remember_many(self, favcat, items):
            remembered.extend((favcat, items))

        async def move_gids(self, gids, target_favcat):
            return len(gids)

    class DummySession:
        def begin(self):
            class DummyCtx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return DummyCtx()

        async def scalars(self, stmt):
            class DummyScalars:
                def all(self):
                    return []

            return DummyScalars()

    async def dummy_get_session():
        yield DummySession()

    monkeypatch.setattr("galleryvault.app.routers.favorites.app_state.eh_client", DummyClient())
    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    res = await favorites_add(FavoritesAddRequest(gid=999, token="tok999", target_favcat=3))
    assert res["target_favcat"] == 3
    assert res["cloud_ok"] is True
    assert res["successful_gids"] == [999]
    assert res["local_added"] == 1
    assert len(remembered) == 2


async def test_favorites_add_endpoint_cloud_failure_does_not_mutate_db(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import favorites_add

    class DummyClient:
        async def add_favorites(self, pairs, target_favcat, note=""):
            return [999]  # failed

    remembered = []

    class DummyRepo:
        def __init__(self, session):
            self.session = session

        async def remember_many(self, favcat, items):
            remembered.extend((favcat, items))

        async def move_gids(self, gids, target_favcat):
            return len(gids)

    class DummySession:
        def begin(self):
            class DummyCtx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return DummyCtx()

        async def scalars(self, stmt):
            class DummyScalars:
                def all(self):
                    return []

            return DummyScalars()

    async def dummy_get_session():
        yield DummySession()

    monkeypatch.setattr("galleryvault.app.routers.favorites.app_state.eh_client", DummyClient())
    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    res = await favorites_add(FavoritesAddRequest(gid=999, token="tok999", target_favcat=3))
    assert res["cloud_ok"] is False
    assert res["cloud_failed"] == [999]
    assert res["successful_gids"] == []
    assert res["local_added"] == 0
    assert len(remembered) == 0  # Crucial: DB never mutated on cloud failure!


async def test_favorites_add_endpoint_exception_does_not_treat_unconfirmed_as_success(
    monkeypatch,
) -> None:
    from galleryvault.app.routers.favorites import favorites_add

    class DummyClient:
        async def add_favorites(self, pairs, target_favcat, note=""):
            raise RuntimeError("boom")

    remembered = []

    class DummyRepo:
        def __init__(self, session):
            self.session = session

        async def remember_many(self, favcat, items):
            remembered.extend((favcat, items))

        async def move_gids(self, gids, target_favcat):
            return len(gids)

    class DummySession:
        def begin(self):
            class DummyCtx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return DummyCtx()

        async def scalars(self, stmt):
            class DummyScalars:
                def all(self):
                    return []

            return DummyScalars()

    async def dummy_get_session():
        yield DummySession()

    monkeypatch.setattr("galleryvault.app.routers.favorites.app_state.eh_client", DummyClient())
    monkeypatch.setattr("galleryvault.app.routers.favorites.FavoritesRepository", DummyRepo)
    monkeypatch.setattr("galleryvault.app.routers.favorites.get_session", dummy_get_session)

    res = await favorites_add(FavoritesAddRequest(gid=999, token="tok999", target_favcat=3))
    assert res["cloud_ok"] is False
    assert res["cloud_failed"] == [999]
    assert res["successful_gids"] == []
    assert res["local_added"] == 0
    assert res["cloud_added"] == 0
    assert len(remembered) == 0


def test_record_favorites_add_log(monkeypatch) -> None:
    from galleryvault.app.routers.favorites import _record_favorites_add_log

    entries: list[dict[str, Any]] = []

    class DummyTM:
        def record_task(self, kind, start, finish, status, reason="", done=0, total=0):
            entries.append({
                "kind": kind,
                "status": status,
                "reason": reason,
                "done": done,
                "total": total,
            })

        async def persist_history(self):
            pass

    monkeypatch.setattr("galleryvault.app.routers.favorites.get_task_manager", lambda: DummyTM())

    _record_favorites_add_log([1, 2], 3, [], 2)
    assert len(entries) == 1
    assert entries[0]["kind"] == "favorites-add"
    assert entries[0]["status"] == "success"
    assert "added 2 to #3" in entries[0]["reason"]

    _record_favorites_add_log([1, 2, 3], 4, [3], 2)
    assert len(entries) == 2
    assert entries[1]["status"] == "failed"
    assert "cloud add failed 1" in entries[1]["reason"]
