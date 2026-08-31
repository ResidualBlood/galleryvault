"""Request correlation ids and a tiny Prometheus-text metrics endpoint.

Deliberately dependency-free: counters, gauges, and histograms are plain module dicts
(the app runs in a single event loop) and the /metrics output is hand-formatted
Prometheus text exposition. Good enough for a single-node self-hosted instance.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.responses import Response

from .logging import _request_id_var

_DEFAULT_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_metrics: dict[str, int] = {}
_gauges: dict[str, float] = {}
_histograms: dict[str, dict[str, Any]] = {}


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


def observe_histogram(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
    buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
) -> None:
    """Observe a value in a Prometheus histogram."""
    key = _format_metric_key(name, labels)
    if key not in _histograms:
        _histograms[key] = {
            "name": name,
            "labels": labels or {},
            "sum": 0.0,
            "count": 0,
            "buckets": {b: 0 for b in buckets},
        }
    entry = _histograms[key]
    entry["sum"] += float(value)
    entry["count"] += 1
    for b in entry["buckets"]:
        if value <= b:
            entry["buckets"][b] += 1


@contextlib.contextmanager
def measure_duration(
    name: str,
    labels: dict[str, str] | None = None,
    buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
):
    """Context manager to measure execution time and record to a histogram."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        observe_histogram(name, elapsed, labels=labels, buckets=buckets)


def _format_metric_key(name: str, labels: dict[str, str] | None) -> str:
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}}"


async def request_id_middleware(request: Request, call_next):
    """Attach X-Request-ID to every response, measure latency, and correlate request logs."""
    rid = uuid4().hex[:12]
    token = _request_id_var.set(rid)
    start_time = time.perf_counter()
    status_code = 500
    try:
        with contextlib.suppress(Exception):
            request.state.request_id = rid
        response: Response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        _bump("gv_http_errors_total")
        raise
    finally:
        elapsed = time.perf_counter() - start_time
        _request_id_var.reset(token)
        if "response" in locals() and response is not None:
            response.headers["X-Request-ID"] = rid
        _bump("gv_http_requests_total")
        _bump(f'gv_http_requests_total{{code="{status_code}"}}')
        observe_histogram("gv_http_request_duration_seconds", elapsed, {"code": str(status_code)})


def render_metrics() -> str:
    """Prometheus text exposition of in-memory counters, gauges, and histograms."""
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

    # Histograms
    histogram_names_seen: set[str] = set()
    for _key, data in sorted(_histograms.items(), key=lambda item: item[0]):
        name = data["name"]
        labels = data["labels"]
        if name not in histogram_names_seen:
            lines.append(f"# HELP {name} Application metric histogram")
            lines.append(f"# TYPE {name} histogram")
            histogram_names_seen.add(name)

        sorted_buckets = sorted(data["buckets"].items(), key=lambda x: x[0])
        for le_val, count in sorted_buckets:
            bucket_labels = dict(labels)
            bucket_labels["le"] = str(le_val)
            lines.append(f"{_format_metric_key(f'{name}_bucket', bucket_labels)} {count}")

        inf_labels = dict(labels)
        inf_labels["le"] = "+Inf"
        lines.append(f"{_format_metric_key(f'{name}_bucket', inf_labels)} {data['count']}")
        lines.append(f"{_format_metric_key(f'{name}_sum', labels)} {data['sum']:.6f}")
        lines.append(f"{_format_metric_key(f'{name}_count', labels)} {data['count']}")

    return "\n".join(lines) + "\n"
