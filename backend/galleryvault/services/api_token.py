"""Bearer API token lifecycle for the companion userscript.

Only a SHA-256 hash of the single token is persisted (in the ``runtime_auth``
extra settings row, next to the auth secret).  The plaintext token is returned
once at generation time and can never be read back.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

from ..db.repository import SettingsRepository
from ..db.session import safe_transaction

TOKEN_HASH_KEY = "api_token_hash"
TOKEN_CREATED_AT_KEY = "api_token_created_at"

_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    """Return the stored representation of a token (never the token itself)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored_hash: Any) -> bool:
    """Constant-time comparison against the persisted hash."""
    if not isinstance(stored_hash, str) or not stored_hash:
        return False
    return hmac.compare_digest(stored_hash, hash_token(token))


async def _read_extra(session: Any | None = None) -> dict[str, Any]:
    if session is not None:
        return await SettingsRepository(session).get_extra()
    # Imported lazily to avoid an import cycle with app.state -> services.
    from ..app.state import app_state

    factory = app_state.session_factory
    if factory is None:
        return {}
    async with factory() as db_session:
        return await SettingsRepository(db_session).get_extra()


async def load_token_metadata(session: Any | None = None) -> dict[str, Any]:
    """Return token state; ``token_hash`` is internal and must not be exposed."""
    extra = await _read_extra(session)
    stored_hash = extra.get(TOKEN_HASH_KEY)
    configured = isinstance(stored_hash, str) and bool(stored_hash)
    return {
        "configured": configured,
        "created_at": extra.get(TOKEN_CREATED_AT_KEY) if configured else None,
        "token_hash": stored_hash if configured else None,
    }


async def create_token(session: Any) -> str:
    """Generate a new token, persist only its hash and return the plaintext once."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    record = {
        TOKEN_HASH_KEY: hash_token(token),
        TOKEN_CREATED_AT_KEY: datetime.now(UTC).isoformat(),
    }
    async with safe_transaction(session):
        await SettingsRepository(session).save_extra(record)
    return token


async def revoke_token(session: Any) -> None:
    """Remove the token; ``save_extra`` merges, so clear the fields explicitly."""
    async with safe_transaction(session):
        await SettingsRepository(session).save_extra({
            TOKEN_HASH_KEY: None,
            TOKEN_CREATED_AT_KEY: None,
        })
