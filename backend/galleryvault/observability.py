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


def _bump(name: str, n: int = 1) -> None:
    _metrics[name] = _metrics.get(name, 0) + n


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
    """Prometheus text exposition of the in-memory counters."""
    lines = ["# HELP gv_http_requests_total HTTP requests served",
             "# TYPE gv_http_requests_total counter"]
    for key, value in sorted(_metrics.items()):
        if key.startswith("gv_http_requests_total"):
            lines.append(f"{key} {value}")
    lines.append("# HELP gv_http_errors_total Requests that raised an exception")
    lines.append("# TYPE gv_http_errors_total counter")
    lines.append(f"gv_http_errors_total {_metrics.get('gv_http_errors_total', 0)}")
    return "\n".join(lines) + "\n"
