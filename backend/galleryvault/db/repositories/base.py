import hashlib
from collections.abc import Sequence
from pathlib import Path


def path_hash(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


# asyncpg binds ~32767 parameters per statement; every ``column.in_(...)`` with
# a caller-supplied list must go through this to stay under the limit.
_CHUNK_SIZE = 500


def escape_like_wildcards(val: str) -> str:
    """Escape SQL LIKE/ILIKE wildcards (%, _, \\) to treat user input as literal text."""
    return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _chunked(values: Sequence[int], size: int = _CHUNK_SIZE) -> list[list[int]]:
    """Split ``values`` into fixed-size slices for ``in_``-style queries."""
    values = list(values)
    return [values[start : start + size] for start in range(0, len(values), size)]
