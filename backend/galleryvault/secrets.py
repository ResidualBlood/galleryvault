"""At-rest encryption for sensitive settings (ExHentai cookies, bot token,
auth secrets).

The key comes from the ``ENCRYPTION_KEY`` environment variable, which is kept
**outside** the database: an encrypted DB dump must not be decryptable from the
dump itself.  Without ``ENCRYPTION_KEY`` the module degrades to a no-op
passthrough so existing deployments keep working unchanged; once the variable
is set, values written from then on are encrypted (``enc:v1:...``) and legacy
plaintext values are still readable on read.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "enc:v1:"
# Fixed salt for at-rest encryption: this is NOT an authentication salt. The
# key is derived from ENCRYPTION_KEY via PBKDF2; a fixed salt means the same
# key always yields the same derived key, which is intentional for at-rest
# protection (the key is the secret, not the salt). Multiple instances sharing
# the same ENCRYPTION_KEY will produce identical ciphertexts for the same
# plaintext — acceptable because the threat model is DB dump theft, not
# multi-instance rainbow. Rotation requires re-encrypting stored values after
# changing ENCRYPTION_KEY; no automated rotation script is provided yet.
_SALT = b"galleryvault-at-rest-v1"
_ITERATIONS = 200_000
_NONCE_BYTES = 12


@lru_cache(maxsize=1)
def _key() -> bytes | None:
    raw = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), _SALT, _ITERATIONS, dklen=32)


def encryption_enabled() -> bool:
    return _key() is not None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(plaintext: str) -> str:
    """Encrypt a string for storage; falls back to plaintext when no key set."""
    key = _key()
    if key is None or not plaintext:
        return plaintext
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip("=")


def decrypt(token: str) -> str:
    """Decrypt an ``enc:v1:`` value; plaintext and malformed values pass through."""
    key = _key()
    if key is None or not token.startswith(PREFIX):
        return token
    try:
        raw = base64.urlsafe_b64decode(
            token[len(PREFIX):] + "=" * (-len(token[len(PREFIX):]) % 4)
        )
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
    except Exception:  # noqa: BLE001 - a corrupt value must not break settings load
        return token


def decrypt_or_plain(value: object) -> object:
    """Decrypt a stored value if it is encrypted, else return it unchanged."""
    return decrypt(value) if is_encrypted(value) else value


def encrypt_json(data: object) -> str:
    """Encrypt a JSON-serializable value (e.g. the cookies dict) for storage."""
    return encrypt(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def decrypt_json_or_value(value: object) -> object:
    """Decrypt an encrypted JSON blob back to its Python value; pass through
    anything that is not an ``enc:v1:`` string."""
    if is_encrypted(value):
        try:
            return json.loads(decrypt(value))
        except (ValueError, TypeError):
            return value
    return value
