"""At-rest encryption for sensitive settings (see galleryvault/secrets.py)."""

from __future__ import annotations

from galleryvault import secrets


def test_encryption_disabled_is_passthrough(monkeypatch) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    secrets._key.cache_clear()
    try:
        assert secrets.encryption_enabled() is False
        assert secrets.encrypt("plain") == "plain"
        assert secrets.decrypt("enc:v1:whatever") == "enc:v1:whatever"
        assert secrets.decrypt_or_plain("plain") == "plain"
    finally:
        secrets._key.cache_clear()


def test_encryption_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-0123456789abcdef0123456789")
    secrets._key.cache_clear()
    try:
        assert secrets.encryption_enabled() is True
        token = secrets.encrypt("secret-value")
        assert token.startswith("enc:v1:")
        assert token != "secret-value"
        assert secrets.is_encrypted(token)
        assert secrets.decrypt(token) == "secret-value"
        # Nonce is random: two encryptions of the same value differ.
        assert secrets.encrypt("secret-value") != token
        # Legacy plaintext and corrupt values pass through unharmed.
        assert secrets.decrypt("legacy-plain") == "legacy-plain"
        assert secrets.decrypt("enc:v1:garbage") == "enc:v1:garbage"
    finally:
        secrets._key.cache_clear()


def test_encrypt_json_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-0123456789abcdef0123456789")
    secrets._key.cache_clear()
    try:
        cookies = {"ipb_member_id": "123", "ipb_pass_hash": "deadbeef", "igneous": "x"}
        blob = secrets.encrypt_json(cookies)
        assert secrets.is_encrypted(blob)
        assert secrets.decrypt_json_or_value(blob) == cookies
        # Non-encrypted values are returned as-is (legacy plaintext dict).
        assert secrets.decrypt_json_or_value({"ipb_member_id": "1"}) == {"ipb_member_id": "1"}
    finally:
        secrets._key.cache_clear()
