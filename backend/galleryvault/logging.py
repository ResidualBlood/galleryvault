import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class _Formatter(logging.Formatter):
    def __init__(self, as_json: bool) -> None:
        super().__init__()
        self.as_json = as_json

    def format(self, record: logging.LogRecord) -> str:
        context = getattr(record, "context", {})
        data = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **context,
        }
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
