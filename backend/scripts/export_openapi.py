"""Export the FastAPI OpenAPI schema to a file.

Usage:
    python scripts/export_openapi.py            # -> docs/openapi.json
    python scripts/export_openapi.py out.json   # custom path

Run it from the backend repository root. The output can be browsed with any
OpenAPI viewer (e.g. https://redocly.github.io/redoc/?url=...).
"""

import json
import sys
from pathlib import Path

from galleryvault.app.main import app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/openapi.json")
    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
