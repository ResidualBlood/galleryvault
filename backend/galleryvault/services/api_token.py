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

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.models import AppConfig
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


async def lock_runtime_auth(session: Any) -> None:
    """Lock the shared ``runtime_auth`` row before merging new values.

    Token writes and password changes both read-modify-write the same JSONB
    value.  Without a row lock a stale reader can write back an old token hash
    after a revoke.  Every in-scope writer must call this inside the same
    transaction as its ``save_extra``.
    """
    execute = getattr(session, "execute", None)
    if execute is None:
        # Lightweight test doubles may not implement session SQL at all.
        return
    # Ensure the shared row exists first, then lock it.  The insert is a no-op
    # when the row already exists and is inside the caller's transaction.
    await execute(
        pg_insert(AppConfig)
        .values(key=SettingsRepository.EXTRA_KEY, value={})
        .on_conflict_do_nothing(index_elements=[AppConfig.key])
    )
    statement = (
        select(AppConfig)
        .where(AppConfig.key == SettingsRepository.EXTRA_KEY)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    await execute(statement)


async def save_runtime_auth(
    session: Any,
    values: dict[str, Any],
    *,
    repository: Any | None = None,
) -> None:
    """Merge ``values`` into ``runtime_auth`` while holding its row lock."""
    async with safe_transaction(session):
        await lock_runtime_auth(session)
        repo = repository if repository is not None else SettingsRepository(session)
        await repo.save_extra(values)


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
    await save_runtime_auth(session, record)
    return token


async def revoke_token(session: Any) -> None:
    """Remove the token; ``save_extra`` merges, so clear the fields explicitly."""
    await save_runtime_auth(session, {
        TOKEN_HASH_KEY: None,
        TOKEN_CREATED_AT_KEY: None,
    })
