import contextvars
import json
import logging
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


def configure_logging(level: str = "INFO", as_json: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter(as_json))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def log_extra(**context: Any) -> dict[str, Any]:
    return {"extra": {"context": context}}
