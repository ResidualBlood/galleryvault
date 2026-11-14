"""The committed OpenAPI snapshot must match the running application.

``backend/docs/openapi.json`` is what API consumers and the docs site read.  It
drifts silently whenever a route is added, removed, or re-pathed.  Comparing the
runtime schema's path+method set keeps the snapshot honest without pinning
descriptions or generated operation ids.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from galleryvault.app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def _operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in schema.get("paths", {}).items()
        for method in item
    }


def test_openapi_snapshot_in_sync() -> None:
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    runtime = app.openapi()

    committed_ops = _operations(committed)
    runtime_ops = _operations(runtime)

    missing = sorted(runtime_ops - committed_ops)
    stale = sorted(committed_ops - runtime_ops)
    assert not missing and not stale, (
        "backend/docs/openapi.json is out of sync with the app; regenerate it with "
        "`python scripts/export_openapi.py` from backend/.\n"
        f"missing from snapshot: {missing}\n"
        f"stale in snapshot: {stale}"
    )
