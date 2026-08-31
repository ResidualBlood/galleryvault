"""Request correlation ids and a tiny Prometheus-text metrics endpoint.

Deliberately dependency-free: the counters are plain module dicts (the app runs
in a single event loop) and the /metrics output is hand-formatted Prometheus
text exposition.  Good enough for a single-node self-hosted instance.
"""

from __future__ import annotations

import contextlib
from uuid import uuid4

from fastapi import Request
from starlette.responses import Response

from .logging import _request_id_var

_metrics: dict[str, int] = {}
_gauges: dict[str, float] = {}


def _bump(name: str, n: int = 1) -> None:
    _metrics[name] = _metrics.get(name, 0) + n


def inc_counter(name: str, n: int = 1, labels: dict[str, str] | None = None) -> None:
    """Increment a Prometheus counter with optional label pairs."""
    key = _format_metric_key(name, labels)
    _metrics[key] = _metrics.get(key, 0) + n


def set_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """Set a Prometheus gauge metric."""
    key = _format_metric_key(name, labels)
    _gauges[key] = value


def _format_metric_key(name: str, labels: dict[str, str] | None) -> str:
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}}"


async def request_id_middleware(request: Request, call_next):
    """Attach X-Request-ID to every response and correlate request logs."""
    rid = uuid4().hex[:12]
    token = _request_id_var.set(rid)
    try:
        with contextlib.suppress(Exception):
            request.state.request_id = rid
        response: Response = await call_next(request)
    except Exception:
        _bump("gv_http_errors_total")
        raise
    finally:
        _request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    _bump("gv_http_requests_total")
    _bump(f'gv_http_requests_total{{code="{response.status_code}"}}')
    return response


def render_metrics() -> str:
    """Prometheus text exposition of in-memory counters and gauges."""
    lines = [
        "# HELP gv_http_requests_total HTTP requests served",
        "# TYPE gv_http_requests_total counter",
    ]
    for key, value in sorted(_metrics.items()):
        if key.startswith("gv_http_requests_total"):
            lines.append(f"{key} {value}")
    lines.append("# HELP gv_http_errors_total Requests that raised an exception")
    lines.append("# TYPE gv_http_errors_total counter")
    lines.append(f"gv_http_errors_total {_metrics.get('gv_http_errors_total', 0)}")

    for key, value in sorted(_metrics.items()):
        if not key.startswith("gv_http_requests_total") and key != "gv_http_errors_total":
            base_name = key.split("{", 1)[0]
            lines.append(f"# HELP {base_name} Application metric counter")
            lines.append(f"# TYPE {base_name} counter")
            lines.append(f"{key} {value}")

    for key, value in sorted(_gauges.items()):
        base_name = key.split("{", 1)[0]
        lines.append(f"# HELP {base_name} Application metric gauge")
        lines.append(f"# TYPE {base_name} gauge")
        lines.append(f"{key} {value}")

    return "\n".join(lines) + "\n"
