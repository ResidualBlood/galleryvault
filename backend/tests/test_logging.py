"""Tests for enhanced logging, formatters, masking, ring buffer, and log level APIs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from galleryvault.app import main
from galleryvault.app.main import app
from galleryvault.config import Settings
from galleryvault.logging import (
    RingBufferHandler,
    _Formatter,
    bind_log_context,
    get_log_level,
    log_extra,
    mask_sensitive,
    set_log_level,
)


def test_mask_sensitive_cookies_and_tokens() -> None:
    raw_str = (
        "Cookie: ipb_member_id=12345; ipb_pass_hash=abcdef1234567890; igneous=9876543210 "
        "and bot token is 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678 "
        "and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    )
    masked = mask_sensitive(raw_str)
    assert "ipb_pass_hash=***" in masked
    assert "ipb_member_id=***" in masked
    assert "igneous=***" in masked
    assert "***:TOKEN***" in masked
    assert "Bearer ***" in masked
    assert "abcdef1234567890" not in masked


def test_mask_sensitive_dictionary() -> None:
    data = {
        "password": "secret_password",
        "auth_secret": "my_secret_key",
        "nested": {
            "token": "token123",
            "normal_field": "hello world",
        },
        "list_field": ["safe", "ipb_pass_hash=deadbeef"],
    }
    masked = mask_sensitive(data)
    assert masked["password"] == "***"
    assert masked["auth_secret"] == "***"
    assert masked["nested"]["token"] == "***"
    assert masked["nested"]["normal_field"] == "hello world"
    assert masked["list_field"][0] == "safe"
    assert masked["list_field"][1] == "ipb_pass_hash=***"


def test_formatter_text_with_exception_and_context() -> None:
    formatter = _Formatter(as_json=False, use_colors=False)
    logger = logging.getLogger("test_text_logger")

    try:
        raise ValueError("test exception trace")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logger.makeRecord(
        name="test_text_logger",
        level=logging.ERROR,
        fn="test_file.py",
        lno=42,
        msg="an error occurred during operation",
        args=(),
        exc_info=exc_info,
        extra=log_extra(gid=123456, task_id=99),
    )

    formatted = formatter.format(record)
    assert "ERROR" in formatted
    assert "test_text_logger: an error occurred during operation" in formatted
    assert "gid=123456" in formatted
    assert "task_id=99" in formatted
    assert "Traceback (most recent call last):" in formatted
    assert "ValueError: test exception trace" in formatted


def test_formatter_json_with_exception() -> None:
    formatter = _Formatter(as_json=True)
    logger = logging.getLogger("test_json_logger")

    try:
        raise RuntimeError("json error test")
    except RuntimeError:
        import sys
        exc_info = sys.exc_info()

    record = logger.makeRecord(
        name="test_json_logger",
        level=logging.ERROR,
        fn="test_file.py",
        lno=100,
        msg="json log message",
        args=(),
        exc_info=exc_info,
        extra=log_extra(gid=999, password="should_be_masked"),
    )

    out = formatter.format(record)
    parsed = json.loads(out)
    assert parsed["level"] == "ERROR"
    assert parsed["logger"] == "test_json_logger"
    assert parsed["message"] == "json log message"
    assert parsed["gid"] == 999
    assert parsed["password"] == "***"
    assert parsed["exception_type"] == "RuntimeError"
    assert "RuntimeError: json error test" in parsed["exception"]


def test_worker_context_binding() -> None:
    formatter = _Formatter(as_json=True)
    logger = logging.getLogger("test_context_logger")

    with bind_log_context(worker="download", task_id=42, gid=888):
        record = logger.makeRecord(
            name="test_context_logger",
            level=logging.INFO,
            fn="worker.py",
            lno=10,
            msg="downloading page 1",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["worker"] == "download"
        assert parsed["task_id"] == 42
        assert parsed["gid"] == 888

    # After leaving context manager, context is reset
    record2 = logger.makeRecord(
        name="test_context_logger",
        level=logging.INFO,
        fn="worker.py",
        lno=10,
        msg="outside context",
        args=(),
        exc_info=None,
    )
    parsed2 = json.loads(formatter.format(record2))
    assert "worker" not in parsed2
    assert "task_id" not in parsed2


def test_ring_buffer_handler() -> None:
    handler = RingBufferHandler(capacity=10)
    test_logger = logging.getLogger("test_ring_buffer")
    test_logger.handlers = [handler]
    test_logger.setLevel(logging.DEBUG)

    test_logger.debug("debug message 1")
    test_logger.info("info message 2", extra=log_extra(tag="important"))
    test_logger.warning("warning message 3")
    try:
        raise KeyError("missing_key")
    except KeyError:
        test_logger.exception("error message 4")

    # Filter by minimum level
    warnings_and_errors = handler.get_logs(min_level="WARNING", limit=10)
    assert len(warnings_and_errors) == 2
    assert warnings_and_errors[0]["level"] == "ERROR"
    assert warnings_and_errors[0]["exception_type"] == "KeyError"
    assert warnings_and_errors[1]["level"] == "WARNING"

    # Filter by search
    searched = handler.get_logs(min_level="DEBUG", search="important")
    assert len(searched) == 1
    assert searched[0]["message"] == "info message 2"

    # Search in exception
    exc_searched = handler.get_logs(min_level="DEBUG", search="missing_key")
    assert len(exc_searched) == 1
    assert exc_searched[0]["level"] == "ERROR"

    # Clear
    handler.clear()
    assert len(handler.get_logs(min_level="DEBUG")) == 0


def test_dynamic_log_level() -> None:
    orig = get_log_level()
    try:
        applied = set_log_level("DEBUG")
        assert applied == "DEBUG"
        assert get_log_level() == "DEBUG"

        applied2 = set_log_level("WARNING")
        assert applied2 == "WARNING"
        assert get_log_level() == "WARNING"
    finally:
        set_log_level(orig)


def test_system_logs_api_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "_settings",
        lambda: Settings(auth_required=False, exhentai_base_url="https://exhentai.org"),
    )
    client = TestClient(app)

    # Log an event into global ring buffer
    logging.getLogger("test_api").warning("system logs api test event", extra=log_extra(source="unit_test"))

    # GET /api/system/logs
    resp = client.get("/api/system/logs?min_level=WARNING&limit=50&search=api+test")
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data
    assert "logs" in data
    assert any("system logs api test event" in item["message"] for item in data["logs"])

    # POST /api/system/logs/level
    orig = data["level"]
    try:
        resp_level = client.post("/api/system/logs/level", json={"level": "DEBUG"})
        assert resp_level.status_code == 200
        assert resp_level.json()["level"] == "DEBUG"

        # Invalid level
        bad_level = client.post("/api/system/logs/level", json={"level": "INVALID_LEVEL"})
        assert bad_level.status_code == 422
    finally:
        set_log_level(orig)

    # DELETE /api/system/logs
    resp_del = client.delete("/api/system/logs")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "cleared"

    # GET /api/system/logs/download
    resp_dl = client.get("/api/system/logs/download")
    assert resp_dl.status_code == 200
    assert "text/plain" in resp_dl.headers.get("content-type", "")
    assert "galleryvault.log" in resp_dl.headers.get("content-disposition", "")


def test_file_rotation_and_hydration(tmp_path: Path) -> None:
    log_file = tmp_path / "test_gv.log"
    handler = RingBufferHandler(capacity=50)

    # Write synthetic log lines into file
    log_file.write_text(
        "2026-09-02T12:00:00+08:00 INFO     test_runner: first historical line [task_id=10]\n"
        "2026-09-02T12:00:01+08:00 WARNING  test_runner: second historical warning [gid=123]\n"
        '{"time": "2026-09-02T12:00:02+08:00", "level": "ERROR", "logger": "json_logger", "message": "json error line", "gid": 456}\n',
        encoding="utf-8",
    )

    handler.hydrate_from_file(log_file, max_lines=10)
    logs = handler.get_logs(min_level="DEBUG", limit=10)

    assert len(logs) == 3
    # logs are ordered newest first
    assert logs[0]["message"] == "json error line"
    assert logs[0]["level"] == "ERROR"
    assert logs[0]["context"]["gid"] == 456

    assert logs[1]["message"] == "second historical warning"
    assert logs[1]["level"] == "WARNING"
    assert logs[1]["context"]["gid"] == "123"

    assert logs[2]["message"] == "first historical line"
    assert logs[2]["level"] == "INFO"
    assert logs[2]["context"]["task_id"] == "10"
