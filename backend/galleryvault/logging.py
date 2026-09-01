from __future__ import annotations

import collections
import contextlib
import contextvars
import json
import logging
import re
import sys
import threading
import time
from datetime import datetime
from typing import Any

# Per-request correlation id (set by the request_id middleware, available to
# every log line emitted while a request is in flight).
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gv_request_id", default=""
)

# Correlation context for background workers / tasks (e.g. task_id, gid, job_type).
_log_context_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "gv_log_context", default=None
)

_SENSITIVE_KEYS = {
    "password",
    "current",
    "auth_secret",
    "encryption_key",
    "secret",
    "token",
    "bot_token",
    "ipb_pass_hash",
    "ipb_member_id",
    "igneous",
    "star",
    "api_key",
    "authorization",
}

_COOKIE_PATTERN = re.compile(
    r"(?i)\b(ipb_pass_hash|ipb_member_id|igneous|star)=([^;\s&]+)"
)
_TELEGRAM_TOKEN_PATTERN = re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{30,}\b")
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9_\-\.]{16,}\b")

_STANDARD_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "context",
    "taskName",
}

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[1;31m",  # Bold Red
}
_RESET_COLOR = "\033[0m"


def request_id() -> str:
    return _request_id_var.get()


def get_log_context() -> dict[str, Any]:
    return dict(_log_context_var.get() or {})


def set_log_context(**kwargs: Any) -> contextvars.Token:
    current = dict(_log_context_var.get() or {})
    current.update(kwargs)
    return _log_context_var.set(current)


def reset_log_context(token: contextvars.Token) -> None:
    _log_context_var.reset(token)


@contextlib.contextmanager
def bind_log_context(**kwargs: Any):
    token = set_log_context(**kwargs)
    try:
        yield
    finally:
        reset_log_context(token)


def mask_sensitive(value: Any) -> Any:
    """Recursively mask known sensitive keys and credential patterns."""
    if isinstance(value, str):
        masked = _COOKIE_PATTERN.sub(r"\1=***", value)
        masked = _TELEGRAM_TOKEN_PATTERN.sub(r"***:TOKEN***", masked)
        return _BEARER_PATTERN.sub(r"\1***", masked)
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                sanitized[k] = "***" if v is not None else None
            else:
                sanitized[k] = mask_sensitive(v)
        return sanitized
    if isinstance(value, (list, tuple)):
        masked_list = [mask_sensitive(item) for item in value]
        return type(value)(masked_list) if isinstance(value, tuple) else masked_list
    return value


def _extract_record_context(record: logging.LogRecord) -> dict[str, Any]:
    context: dict[str, Any] = dict(_log_context_var.get() or {})
    direct_context = getattr(record, "context", None)
    if isinstance(direct_context, dict):
        context.update(direct_context)
    for key, val in record.__dict__.items():
        if key not in _STANDARD_LOG_RECORD_ATTRS and not key.startswith("_"):
            context[key] = val
    return mask_sensitive(context)


class _Formatter(logging.Formatter):
    def __init__(self, as_json: bool, use_colors: bool | None = None) -> None:
        super().__init__()
        self.as_json = as_json
        if use_colors is None:
            self.use_colors = not as_json and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        else:
            self.use_colors = use_colors and not as_json

    def format(self, record: logging.LogRecord) -> str:
        context = _extract_record_context(record)
        message = mask_sensitive(record.getMessage())
        rid = _request_id_var.get() or context.pop("request_id", None)

        formatted_exc: str | None = None
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            formatted_exc = record.exc_text

        formatted_stack: str | None = None
        if record.stack_info:
            formatted_stack = self.formatStack(record.stack_info)

        if self.as_json:
            data = {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
                **context,
            }
            if rid:
                data["request_id"] = rid
            if formatted_exc:
                data["exception"] = formatted_exc
                if record.exc_info and record.exc_info[0]:
                    data["exception_type"] = record.exc_info[0].__name__
            if formatted_stack:
                data["stack_info"] = formatted_stack
            return json.dumps(data, ensure_ascii=False, default=str)

        level_str = record.levelname
        if self.use_colors:
            color = _LEVEL_COLORS.get(record.levelname, "")
            level_str = f"{color}{record.levelname:<8}{_RESET_COLOR}"
        else:
            level_str = f"{record.levelname:<8}"

        now_str = datetime.now().astimezone().isoformat(timespec="seconds")
        prefix = f"{now_str} {level_str} {record.name}: {message}"
        if rid:
            context["request_id"] = rid

        suffix = " ".join(f"{key}={value!r}" for key, value in context.items())
        line = f"{prefix}" + (f" [{suffix}]" if suffix else "")
        if formatted_exc:
            line += f"\n{formatted_exc}"
        if formatted_stack:
            line += f"\n{formatted_stack}"
        return line


class _HttpAccessFilter(logging.Filter):
    """Suppress noisy access logs that carry no diagnostic value.

    - httpx access logs for successful (2xx/3xx) requests: httpx logs one INFO
      line per request ("HTTP Request: GET <url> \"HTTP/1.1 200 OK\"").
      Download-heavy workloads flood stdout with thousands of 200s. Keep
      4xx/5xx (real failures worth diagnosing) while dropping 2xx/3xx.
    - uvicorn healthcheck heartbeats: the docker healthcheck polls /healthz
      every ~10s, so uvicorn.access emits one line per poll. Real API access
      logs (any non-/healthz path) are kept.
    """

    _STATUS = re.compile(r'"HTTP/\d(?:\.\d)? (\d{3})')
    _HEALTHZ = re.compile(r'"GET /healthz ')

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno > logging.INFO:
            return True
        if record.name == "httpx":
            match = self._STATUS.search(record.getMessage())
            if match and match.group(1)[0] in "23":
                return False
        elif record.name == "uvicorn.access" and self._HEALTHZ.search(record.getMessage()):
            return False
        return True


_default_formatter = logging.Formatter()


class RingBufferHandler(logging.Handler):
    """Stores the latest N formatted log entries in memory for diagnostic retrieval."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self.capacity = capacity
        self.buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted_exc: str | None = None
            exc_type: str | None = None
            if record.exc_info:
                if not record.exc_text:
                    record.exc_text = _default_formatter.formatException(record.exc_info)
                formatted_exc = record.exc_text
                if record.exc_info[0]:
                    exc_type = record.exc_info[0].__name__

            context = _extract_record_context(record)
            rid = _request_id_var.get() or context.pop("request_id", None)
            entry: dict[str, Any] = {
                "id": 0,
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "timestamp": time.time(),
                "level": record.levelname,
                "levelno": record.levelno,
                "logger": record.name,
                "message": mask_sensitive(record.getMessage()),
                "request_id": rid,
                "context": context,
                "exception": formatted_exc,
                "exception_type": exc_type,
            }

            with self._lock:
                self._seq += 1
                entry["id"] = self._seq
                self.buffer.append(entry)
        except Exception:  # noqa: S110, BLE001
            pass

    def get_logs(
        self,
        min_level: str = "INFO",
        limit: int = 100,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        threshold = getattr(logging, min_level.upper(), logging.INFO)
        search_term = search.lower() if search else None

        with self._lock:
            entries = list(self.buffer)

        results: list[dict[str, Any]] = []
        for item in reversed(entries):
            if item["levelno"] < threshold:
                continue
            if search_term:
                match = (
                    search_term in item["message"].lower()
                    or search_term in item["logger"].lower()
                    or (item["exception"] and search_term in item["exception"].lower())
                    or (item["context"] and search_term in str(item["context"]).lower())
                )
                if not match:
                    continue
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def clear(self) -> None:
        with self._lock:
            self.buffer.clear()


_ring_buffer_handler = RingBufferHandler(capacity=1000)


def get_recent_logs(
    min_level: str = "INFO", limit: int = 100, search: str | None = None
) -> list[dict[str, Any]]:
    return _ring_buffer_handler.get_logs(min_level=min_level, limit=limit, search=search)


def clear_recent_logs() -> None:
    _ring_buffer_handler.clear()


def get_log_level() -> str:
    return logging.getLevelName(logging.getLogger().level)


def set_log_level(level: str) -> str:
    lvl = level.upper()
    numeric_level = getattr(logging, lvl, None)
    if numeric_level is None:
        raise ValueError(f"Invalid log level: {level}")
    root = logging.getLogger()
    root.setLevel(numeric_level)
    for handler in root.handlers:
        handler.setLevel(numeric_level)
    # Also update uvicorn loggers if present
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(numeric_level)
    return lvl


def configure_logging(
    level: str = "INFO", as_json: bool = False, use_colors: bool | None = None
) -> None:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(_Formatter(as_json, use_colors=use_colors))
    access_filter = _HttpAccessFilter()
    stream_handler.addFilter(access_filter)

    root = logging.getLogger()
    root.handlers[:] = [stream_handler, _ring_buffer_handler]
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    # uvicorn installs its own handler on the "uvicorn.access" logger (with
    # propagate=False), so access-log records never pass through the root
    # handler's filter. Attach the filter to the logger as well so /healthz
    # heartbeats are silenced regardless of which handler uvicorn uses.
    logging.getLogger("uvicorn.access").addFilter(access_filter)


def log_extra(**context: Any) -> dict[str, Any]:
    # Returned dict is passed as ``extra=`` to a logging call; logging merges it
    # into the LogRecord. ``_Formatter`` then reads ``record.context`` for the
    # ``[key=value ...]`` suffix / JSON object.
    return {"context": context}
