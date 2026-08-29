import contextvars
import json
import logging
import re
import sys
from datetime import datetime
from typing import Any

# Per-request correlation id (set by the request_id middleware, available to
# every log line emitted while a request is in flight).
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gv_request_id", default=""
)


def request_id() -> str:
    return _request_id_var.get()


class _Formatter(logging.Formatter):
    def __init__(self, as_json: bool) -> None:
        super().__init__()
        self.as_json = as_json

    def format(self, record: logging.LogRecord) -> str:
        context = getattr(record, "context", {})
        data = {
            # Local time (container TZ, e.g. Asia/Shanghai) so log timestamps
            # match the system clock.
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **context,
        }
        rid = _request_id_var.get()
        if rid:
            data["request_id"] = rid
        if self.as_json:
            return json.dumps(data, ensure_ascii=False, default=str)
        suffix = " ".join(f"{key}={value!r}" for key, value in context.items())
        return f"{data['time']} {record.levelname:<8} {record.name}: {data['message']}" + (
            f" [{suffix}]" if suffix else ""
        )


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


def configure_logging(level: str = "INFO", as_json: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter(as_json))
    handler.addFilter(_HttpAccessFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def log_extra(**context: Any) -> dict[str, Any]:
    # Returned dict is passed as ``extra=`` to a logging call; logging merges it
    # into the LogRecord. ``_Formatter`` then reads ``record.context`` for the
    # ``[key=value ...]`` suffix / JSON object. (A nested ``{"extra": {...}}``
    # here would set ``record.extra`` and silently drop every field.)
    return {"context": context}
