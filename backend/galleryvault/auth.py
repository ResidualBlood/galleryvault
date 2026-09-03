"""Password hashing and stateless signed session cookies."""

import asyncio
import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import secrets
import sys
import time
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import RedirectResponse

ALGORITHM = "sha256"
ITERATIONS = 310_000
DEFAULT_PASSWORD = "p1a2s3s4"

LOGIN_RATE_WINDOW = 60.0
LOGIN_RATE_MAX = 10
_login_attempts: dict[str, list[float]] = {}
_login_lock = asyncio.Lock()


async def login_gate(ip: str) -> bool:
    """Return True if ip may attempt a login within the rate window."""
    global _login_attempts
    ip = str(ip)[:64]
    now = time.time()
    async with _login_lock:
        if len(_login_attempts) > 2048:
            cutoff = now - LOGIN_RATE_WINDOW
            _login_attempts = {
                key: [t for t in stamps if t >= cutoff]
                for key, stamps in _login_attempts.items()
                if any(t >= cutoff for t in stamps)
            }
        stamps = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_RATE_WINDOW]
        if len(stamps) >= LOGIN_RATE_MAX:
            return False
        _login_attempts[ip] = stamps + [now]
    return True


async def login_succeeded(ip: str) -> None:
    ip = str(ip)[:64]
    async with _login_lock:
        _login_attempts.pop(ip, None)


def is_trusted_proxy(host: str | None) -> bool:
    if not host:
        return False
    if host in {"testclient", "localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return True
        # Private networks are NOT trusted by default — only explicit whitelist.
        try:
            from .app.state import app_state
            settings = app_state.settings
        except Exception:  # noqa: BLE001
            settings = None
        if settings is None:
            from .config import get_settings
            settings = get_settings()
        trusted = getattr(settings, "trusted_proxies", None) or []
        for entry in trusted:
            entry = str(entry).strip()
            if not entry:
                continue
            if "/" in entry:
                try:
                    net = ipaddress.ip_network(entry, strict=False)
                    if ip in net:
                        return True
                except ValueError:
                    continue
            else:
                try:
                    if ip == ipaddress.ip_address(entry):
                        return True
                except ValueError:
                    if host == entry:
                        return True
        return False
    except ValueError:
        return False


def client_ip(request: Request) -> str:
    """Best-effort real client IP for login rate limiting."""
    peer = request.client.host if request.client else "unknown"
    if is_trusted_proxy(peer):
        real = request.headers.get("x-real-ip")
        if real and len(real) <= 128 and real.strip():
            candidate = real.strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and len(forwarded) <= 512 and forwarded.strip():
            parts = [p.strip() for p in forwarded.split(",")][:16]
            for part in parts:
                if part and len(part) <= 64:
                    try:
                        ipaddress.ip_address(part)
                        return part
                    except ValueError:
                        pass
    return str(peer)[:64]


def verify_login_password(password: str, effective: str | None) -> bool:
    if effective is None:
        return hmac.compare_digest(password, DEFAULT_PASSWORD)
    if effective.startswith("pbkdf2_sha256$"):
        return verify_password(password, effective)
    return hmac.compare_digest(password, effective)


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
        if iterations < 200_000 or iterations > 10_000_000:
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
