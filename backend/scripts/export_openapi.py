"""Export the FastAPI OpenAPI schema to a file, or verify the committed one.

Usage:
    python scripts/export_openapi.py            # -> docs/openapi.json
    python scripts/export_openapi.py out.json   # custom path
    python scripts/export_openapi.py --check    # fail if docs/openapi.json is stale

Run it from the backend repository root. The output can be browsed with any
OpenAPI viewer (e.g. https://redocly.github.io/redoc/?url=...).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from galleryvault.app.main import app


def _operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in schema.get("paths", {}).items()
        for method in item
    }


def _check(out: Path, runtime: dict[str, Any]) -> int:
    if not out.exists():
        print(f"missing OpenAPI snapshot: {out}", file=sys.stderr)
        return 1
    committed = json.loads(out.read_text(encoding="utf-8"))
    committed_ops = _operations(committed)
    runtime_ops = _operations(runtime)
    missing = sorted(runtime_ops - committed_ops)
    stale = sorted(committed_ops - runtime_ops)
    if not missing and not stale:
        print(f"{out} is in sync ({len(runtime_ops)} operations)")
        return 0
    print(f"{out} is out of sync with the running app", file=sys.stderr)
    for label, operations in (("missing", missing), ("stale", stale)):
        for method, path in operations:
            print(f"  {label}: {method} {path}", file=sys.stderr)
    return 1


def main() -> int:
    args = list(sys.argv[1:])
    check = bool(args) and args[0] == "--check"
    if check:
        args = args[1:]
    out = Path(args[0] if args else "docs/openapi.json")

    schema = app.openapi()
    if check:
        return _check(out, schema)

    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
