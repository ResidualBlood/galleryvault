from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import InvalidRequestError

from galleryvault.app.main import app
from galleryvault.app.routers import settings as settings_router
from galleryvault.app.routers.settings import settings_save
from galleryvault.app.schemas import SettingsRequest
from galleryvault.app.state import app_state
from galleryvault.db.models import FavoritesMonitor
from galleryvault.db.session import safe_transaction


class StrictTransactionSession:
    """模拟真实 SQLAlchemy 2.0 AsyncSession 的事务状态机与 autobegin 行为。

    - 任何 SELECT 或读取操作会隐式开启事务（autobegin），导致 in_transaction() == True。
    - 若在 in_transaction() == True 时调用 session.begin()，严格抛出 InvalidRequestError。
    - 通过 safe_transaction 可以安全在处于事务中的 session 上完成提交，避免抛错。
    """

    def __init__(self) -> None:
        self._in_trans: bool = False
        self.commit_count: int = 0
        self.rollback_count: int = 0
        self.added: list[Any] = []
        self.saved_settings: dict[str, Any] = {}

    def in_transaction(self) -> bool:
        return self._in_trans

    def trigger_select_autobegin(self) -> None:
        """模拟 SELECT 查询导致的 autobegin。"""
        self._in_trans = True

    def begin(self):
        if self._in_trans:
            raise InvalidRequestError(
                "A transaction is already begun on this Session. "
                "Use subtransactions=True or nested transactions for nested begin() blocks."
            )
        self._in_trans = True

        class _BeginCtx:
            def __init__(self, parent: StrictTransactionSession) -> None:
                self.parent = parent

            async def __aenter__(self):
                return self.parent

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type is not None:
                    self.parent.rollback_count += 1
                    self.parent._in_trans = False
                    return False
                self.parent.commit_count += 1
                self.parent._in_trans = False
                return False

        return _BeginCtx(self)

    async def commit(self) -> None:
        self.commit_count += 1
        self._in_trans = False

    async def rollback(self) -> None:
        self.rollback_count += 1
        self._in_trans = False

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def close(self) -> None:
        pass


class FakeSettingsRepo:
    def __init__(self, session: StrictTransactionSession) -> None:
        self.session = session

    async def get(self) -> dict[str, Any]:
        # 模拟真实 SELECT 查询触发 autobegin
        self.session.trigger_select_autobegin()
        return dict(self.session.saved_settings)

    async def save(self, data: dict[str, Any]) -> None:
        self.session.saved_settings.update(data)


class FakeFavoritesRepo:
    def __init__(self, session: StrictTransactionSession) -> None:
        self.session = session

    async def category(self, favcat: int) -> FavoritesMonitor | None:
        # 查询操作保持/触发事务
        self.session.trigger_select_autobegin()
        for item in self.session.added:
            if isinstance(item, FavoritesMonitor) and item.favcat == favcat:
                return item
        return None


def _noop_spawn(coro: Any, name: str) -> None:
    try:
        coro.close()
    except Exception:  # noqa: BLE001, S110
        pass


@pytest.mark.asyncio
async def test_save_favorites_settings_reusing_session_after_select_no_503(monkeypatch):
    """验证在复用同一个 session（在经过 SELECT 后）调用保存配置端点（POST /api/settings，
    传入 favorites 监控配置），不会报 503 InvalidRequestError / Database is unavailable，
    能够正常返回 200 成功保存。
    """
    session = StrictTransactionSession()

    # 1. 模拟前置操作已执行 SELECT，触发 autobegin 使 session 进入处于事务状态
    session.trigger_select_autobegin()
    assert session.in_transaction() is True

    # 验证如果在此状态下直接调用 begin()，必定会抛出 InvalidRequestError
    with pytest.raises(InvalidRequestError, match="A transaction is already begun on this Session"):
        async with session.begin():
            pass

    # 保持 session.in_transaction() 为 True
    session.trigger_select_autobegin()
    assert session.in_transaction() is True

    monkeypatch.setattr(settings_router, "SettingsRepository", FakeSettingsRepo)
    monkeypatch.setattr(settings_router, "FavoritesRepository", FakeFavoritesRepo)
    monkeypatch.setattr(settings_router, "refresh_services", AsyncMock())
    monkeypatch.setattr(settings_router, "spawn_task", _noop_spawn)

    # 2. 构造 favorites 监控配置 payload
    favorites_config = [
        {
            "favcat": 1,
            "enabled": True,
            "mode": "incremental",
            "poll_interval_minutes": 120,
        },
        {
            "favcat": 2,
            "enabled": False,
            "mode": "monitor_only",
            "poll_interval_minutes": 60,
        },
    ]
    request_body = SettingsRequest(favorites=favorites_config)

    # 3. 直接调用端点保存函数（复用同一个已在事务中的 session）
    result = await settings_save(body=request_body, session=session)

    # 4. 验证未报 503 异常，正常返回 200 结果
    assert isinstance(result, dict)
    assert session.commit_count >= 1
    assert session.in_transaction() is False

    # 5. 验证添加到了 session 中的 FavoritesMonitor
    added_monitors = [item for item in session.added if isinstance(item, FavoritesMonitor)]
    assert len(added_monitors) == 2
    favcat1 = next(m for m in added_monitors if m.favcat == 1)
    assert favcat1.enabled is True
    assert favcat1.mode == "incremental"
    assert favcat1.poll_interval_seconds == 120 * 60


def test_post_settings_api_http_client_with_favorites_success(monkeypatch):
    """通过 TestClient 模拟 HTTP POST /api/settings，验证在 session 经过 SELECT
    进入隐式事务后保存收藏夹配置，HTTP 响应状态码为 200 成功而非 503。
    """
    session = StrictTransactionSession()
    # 模拟前置 SELECT 使 session.in_transaction() 为 True
    session.trigger_select_autobegin()

    monkeypatch.setattr(settings_router, "SettingsRepository", FakeSettingsRepo)
    monkeypatch.setattr(settings_router, "FavoritesRepository", FakeFavoritesRepo)
    monkeypatch.setattr(settings_router, "refresh_services", AsyncMock())
    monkeypatch.setattr(settings_router, "spawn_task", _noop_spawn)

    # 临时关闭认证要求以方便通过 TestClient 测试路由逻辑
    if app_state.settings:
        monkeypatch.setattr(app_state.settings, "auth_required", False)

    async def fake_get_session():
        yield session

    app.dependency_overrides[settings_router.get_session] = fake_get_session
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/settings",
                json={
                    "favorites": [
                        {
                            "favcat": 0,
                            "enabled": True,
                            "mode": "monitor_only",
                            "poll_interval_minutes": 30,
                        }
                    ]
                },
            )
        assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict)
        assert session.commit_count >= 1
    finally:
        app.dependency_overrides.pop(settings_router.get_session, None)


@pytest.mark.asyncio
async def test_safe_transaction_protects_against_nested_begin_error():
    """单元验证 safe_transaction：在 session 处于事务中时正确 commit 而不触发 begin 异常。"""
    session = StrictTransactionSession()
    session.trigger_select_autobegin()
    assert session.in_transaction() is True

    # safe_transaction 能够正常进入并在退出时 commit
    async with safe_transaction(session):
        session.saved_settings["key"] = "value"

    assert session.commit_count == 1
    assert session.in_transaction() is False
    assert session.saved_settings["key"] == "value"
