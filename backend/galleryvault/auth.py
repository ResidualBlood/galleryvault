"""Password hashing and stateless signed session cookies."""

import base64
import getpass
import hashlib
import hmac
import json
import secrets
import sys
import time
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import RedirectResponse

ALGORITHM = "sha256"
ITERATIONS = 310_000


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(ALGORITHM, password.encode(), salt, iterations)
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return f"pbkdf2_sha256${iterations}${encode(salt)}${encode(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        scheme, raw_iterations, raw_salt, raw_digest = (encoded or "").split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        if iterations < 100_000 or iterations > 10_000_000:
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        expected = hashlib.pbkdf2_hmac(ALGORITHM, password.encode(), decode(raw_salt), iterations)
        return hmac.compare_digest(expected, decode(raw_digest))
    except (ValueError, TypeError):
        return False


def _signature(payload: str, secret: str) -> str:
    return (
        base64.urlsafe_b64encode(
            hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        .decode()
        .rstrip("=")
    )


def create_session(secret: str, ttl: int) -> str:
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) + ttl}, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    return f"{payload}.{_signature(payload, secret)}"


def verify_session(value: str | None, secret: str) -> bool:
    try:
        payload, signature = (value or "").split(".", 1)
        if not hmac.compare_digest(signature, _signature(payload, secret)):
            return False
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        return int(json.loads(decoded)["exp"]) > int(time.time())
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


async def login_password(request: Request) -> str:
    body = await request.body()
    return parse_qs(body.decode(), keep_blank_values=True).get("password", [""])[0]


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


if __name__ == "__main__" and len(sys.argv) >= 2 and sys.argv[1] == "hash-password":
    password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Password: ")
    print(hash_password(password))
