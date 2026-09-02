import os

os.environ.setdefault("GALLERYVAULT_ENABLE_WORKERS", "0")

import pytest

from galleryvault.app.state import app_state


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
