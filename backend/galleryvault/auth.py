"""Password hashing and stateless signed session cookies."""

import asyncio
import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import sys
import time
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import RedirectResponse

from .logging import log_extra

logger = logging.getLogger(__name__)

ALGORITHM = "sha256"
ITERATIONS = 310_000
DEFAULT_PASSWORD = "p1a2s3s4"

LOGIN_RATE_WINDOW = 60.0
LOGIN_RATE_MAX = 10

# There is one administrator account. Its process-local backoff is shared by
# all source IPs, in addition to the independent per-IP rate window.
ACCOUNT_FAILURE_WINDOW = 900.0
ACCOUNT_FAILURE_THRESHOLD = 5
ACCOUNT_LOCK_BASE_SECONDS = 5.0
ACCOUNT_LOCK_MAX_SECONDS = 900.0

_login_attempts: dict[str, list[float]] = {}
_login_lock = asyncio.Lock()
_account_failures: dict[str, list[float]] = {}
_account_locked_until: dict[str, float] = {}


async def account_lock_remaining(ip: str) -> float:
    """Seconds the single administrator account is locked (0 when unlocked)."""
    ip = "admin"
    now = time.time()
    async with _login_lock:
        remaining = _account_locked_until.get(ip, 0.0) - now
        if remaining <= 0:
            _account_locked_until.pop(ip, None)
            return 0.0
        return float(remaining)


async def login_failed(ip: str) -> float:
    """Record a failed password and return the lockout seconds applied (0 = none)."""
    global _account_failures
    ip = "admin"
    now = time.time()
    async with _login_lock:
        cutoff = now - ACCOUNT_FAILURE_WINDOW
        stamps = [t for t in _account_failures.get(ip, []) if t >= cutoff]
        stamps.append(now)
        if len(_account_failures) > 2048:
            _account_failures = {
                key: [t for t in values if t >= cutoff]
                for key, values in _account_failures.items()
                if any(t >= cutoff for t in values)
            }
        _account_failures[ip] = stamps
        failures = len(stamps)
        if failures < ACCOUNT_FAILURE_THRESHOLD:
            return 0.0
        extra = min(failures - ACCOUNT_FAILURE_THRESHOLD, 8)
        delay = min(ACCOUNT_LOCK_MAX_SECONDS, ACCOUNT_LOCK_BASE_SECONDS * (2**extra))
        locked_until = max(_account_locked_until.get(ip, 0.0), now + delay)
        _account_locked_until[ip] = locked_until
        return float(locked_until - now)


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
        _account_failures.pop("admin", None)
        _account_locked_until.pop("admin", None)


_auth_bootstrap_done = False
_auth_bootstrap_lock: asyncio.Lock | None = None


def reset_runtime_auth_bootstrap() -> None:
    """Forget the one-shot DB auth-secret lookup (tests / explicit reloads)."""
    global _auth_bootstrap_done, _auth_bootstrap_lock
    _auth_bootstrap_done = False
    _auth_bootstrap_lock = None


async def ensure_runtime_auth_secret() -> None:
    """Adopt the DB-persisted session secret on first use.

    ``GALLERYVAULT_ENABLE_WORKERS=0`` skips the startup bootstrap in
    ``app/lifespan.py``, so every process would keep the random session secret
    generated in ``config.Settings.model_post_init``.  With several uvicorn
    workers that means cookies signed by one process are rejected by the next
    (random 401 / login loops).  Reading the persisted secret lazily — before
    the first request is authenticated — gives every process the same value
    without changing the startup sequence.

    Only runs for process-generated secrets. Database failures propagate so a
    worker cannot issue cookies using a private, inconsistent secret.
    """
    global _auth_bootstrap_done, _auth_bootstrap_lock
    if _auth_bootstrap_done:
        return
    if _auth_bootstrap_lock is None:
        _auth_bootstrap_lock = asyncio.Lock()
    async with _auth_bootstrap_lock:
        if _auth_bootstrap_done:
            return
        try:
            from .app.state import app_state
        except Exception:  # noqa: BLE001
            _auth_bootstrap_done = True
            return
        settings = getattr(app_state, "settings", None)
        if settings is None:
            return
        if (
            not getattr(settings, "auth_secret_ephemeral", False)
            or settings.auth_secret != settings._generated_auth_secret
        ):
            # Explicit AUTH_SECRET (or a secret already restored by the startup
            # bootstrap): nothing to resolve from the database.
            _auth_bootstrap_done = True
            return
        factory = getattr(app_state, "session_factory", None)
        if factory is None:
            return
        try:
            from sqlalchemy import select, text
            from sqlalchemy.dialects.postgresql import insert

            from .db.models import AppConfig
            from .db.session import safe_transaction
            from .secrets import decrypt_or_plain, encrypt, encryption_enabled

            async with factory() as session, safe_transaction(session):
                # Bound first-request waiting, including during DB outages.
                await session.execute(text("SET LOCAL lock_timeout = '3s'"))
                await session.execute(
                    insert(AppConfig).values(key="runtime_auth", value={}).on_conflict_do_nothing(
                        index_elements=[AppConfig.key]
                    )
                )
                row = (await session.execute(
                    select(AppConfig).where(AppConfig.key == "runtime_auth").with_for_update()
                )).scalar_one()
                runtime = dict(row.value or {})
                raw = runtime.get("auth_secret")
                secret = decrypt_or_plain(raw) if isinstance(raw, str) and raw else None
                if not secret:
                    secret = settings.auth_secret
                    runtime["auth_secret"] = encrypt(secret) if encryption_enabled() else secret
                    row.value = runtime
            logger.info("session secret restored from database")
        except Exception as exc:
            logger.warning(
                "could not resolve the persisted session secret",
                extra=log_extra(error=type(exc).__name__),
            )
            raise
        if app_state.settings is not None:
            app_state.settings = app_state.settings.model_copy(
                update={
                    "auth_secret": secret or app_state.settings.auth_secret,
                    "auth_secret_ephemeral": False,
                }
            )
        _auth_bootstrap_done = True


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
    if not effective:
        # No password configured. This helper is used by the OPDS/cbz Basic Auth
        # path, which must never fall back to the baked-in default; only the
        # interactive /login handler may accept DEFAULT_PASSWORD for first-run
        # onboarding (see app/routers/auth.py).
        return False
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
