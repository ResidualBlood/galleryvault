import asyncio
import hashlib
import inspect
import os
import warnings

os.environ.setdefault("GALLERYVAULT_ENABLE_WORKERS", "0")

# 统一忽略非关键的 asyncpg connection._cancel unawaited 垃圾回收告警
warnings.filterwarnings("ignore", message=r".*Connection\._cancel.*", category=RuntimeWarning)

# Passlib PBKDF2 iterations optimization (if installed)
try:
    from passlib.handlers.pbkdf2 import pbkdf2_sha256

    if hasattr(pbkdf2_sha256, "default_rounds"):
        pbkdf2_sha256.default_rounds = 1
except ImportError:
    pass

# Global fast PBKDF2: reduce PBKDF2 HMAC iterations to 1 to eliminate CPU cost in test suite
_orig_pbkdf2_hmac = hashlib.pbkdf2_hmac


def _fast_pbkdf2_hmac(hash_name, password, salt, iterations, dklen=None):
    if dklen is not None:
        return _orig_pbkdf2_hmac(hash_name, password, salt, 1, dklen)
    return _orig_pbkdf2_hmac(hash_name, password, salt, 1)


hashlib.pbkdf2_hmac = _fast_pbkdf2_hmac

import pytest

from galleryvault.app.main import app  # noqa: F401
from galleryvault.app.state import app_state


@pytest.fixture(autouse=True)
def _fast_asyncio_sleep(monkeypatch):
    """Automatically mock asyncio.sleep to eliminate hard sleep / backoff delays while preserving event loop tick."""
    _orig_sleep = asyncio.sleep

    async def _fast_sleep(delay=0, result=None, *args, **kwargs):
        # 仅跳过下载与重试的等待（downloader, download_worker 及后台重试 backoff）
        frame = inspect.currentframe().f_back
        filename = frame.f_code.co_filename if frame else ""
        if "downloader.py" in filename or "download_worker.py" in filename or (delay >= 1.0 and "test_" not in filename):
            await _orig_sleep(0)
            return result
        return await _orig_sleep(delay, result, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


@pytest.fixture(autouse=True)
def _isolate_app_state():
    """隔离每个测试对全局 app_state 和 app.state 的修改，防止状态泄露。"""
    orig_settings = app_state.settings
    orig_session_factory = app_state.session_factory
    orig_eh_client = app_state.eh_client
    orig_telegram = app_state.telegram
    orig_extra = dict(app_state.extra)

    # 单元测试默认隔离 worker 连接池，避免跨 loop 污染及打到真实 DB
    if app_state.worker_engine is not None:
        try:
            app_state.worker_engine.sync_engine.dispose()
        except Exception:
            pass
    app_state.worker_engine = None
    app_state.worker_session_factory = None

    yield

    app_state.reset()
    app_state.settings = orig_settings
    app_state.session_factory = orig_session_factory
    app_state.eh_client = orig_eh_client
    app_state.telegram = orig_telegram
    app_state.extra = orig_extra
    try:
        from galleryvault.app.main import app

        app.state.settings = orig_settings
        app.state.worker_engine = None
        app.state.worker_session_factory = None
    except (ImportError, AttributeError):
        pass


def bind_runtime(**kwargs):
    """测试唯一入口：写入 app_state，并镜像到 app.state（若已创建）。"""
    for k, v in kwargs.items():
        setattr(app_state, k, v)
    from galleryvault.app.main import app
    from galleryvault.app.state import sync_state

    sync_state(app)
    return app


@pytest.fixture
def runtime():
    return bind_runtime
