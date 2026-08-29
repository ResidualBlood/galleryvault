import json
import logging
import os
import secrets
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://galleryvault:galleryvault@db:5432/galleryvault"
    )
    library_roots: list[str] = Field(default_factory=lambda: ["/library", "/downloads"])
    download_root: str = "/downloads"
    thumbnail_cache_dir: str = "/gv-cache/thumbs"
    generate_thumbnails: bool = True
    log_level: str = "INFO"
    log_json: bool = False
    scan_batch_size: int = 500
    auth_secret: str | None = None
    auth_password_hash: str | None = None
    auth_password: str | None = None
    auth_required: bool = True
    auth_cookie_name: str = "galleryvault_session"
    auth_session_ttl: int = 86400
    auth_cookie_secure: bool = False
    tag_translation_update_interval_minutes: int = 720
    exhentai_base_url: str = "https://exhentai.org"
    exhentai_cookies: dict[str, str] = Field(default_factory=dict)
    http_proxy: str | None = None
    socks5_proxy: str | None = None
    download_quality: str = "resample"
    use_hah: bool = True
    download_concurrency: int = 2
    # Pages fetched in parallel per gallery. H@H nodes limit concurrent
    # connections per source IP (roughly 4-6), so defaulting low avoids a
    # connect-error storm on lossy proxy paths; user-tunable via settings.
    page_concurrency: int = 4
    # Watchdogs for slow H@H image nodes: a total wall-clock budget per image,
    # a minimum average throughput enforced after a short warm-up window, and
    # the warm-up itself.  A node that trickles a few KB/s without ever going
    # fully idle would otherwise hold a download worker for many minutes.
    image_download_timeout_seconds: int = 120
    image_slow_warmup_seconds: int = 10
    image_min_speed_kb_s: int = 50
    # Cap on parallel ExHentai requests across ALL background workers (tag
    # sync, downloads, favorites, covers). Kept low to avoid tripping
    # ExHentai's anti-abuse when several tasks run at once.
    exhentai_max_concurrency: int = 6
    title_display: str = "japanese"
    auto_sync_tags: bool = True
    tag_sync_interval_seconds: float = 1.5
    tag_sync_concurrency: int = Field(default=4, ge=1, le=32)
    favorites_poll_interval_minutes: int = 720
    telegram_bot_token: str | None = None
    telegram_chat_ids: list[str] = Field(default_factory=list)
    telegram_allowed_user_ids: list[int] = Field(default_factory=list)
    telegram_notify_level: str = "summary"
    telegram_notify_lang: str = "zh"
    favorites_categories: list[int] = Field(default_factory=lambda: list(range(8)))
    download_favorites_enabled: bool = False
    duplicate_policy: str = "keep_first"
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    @field_validator("library_roots", mode="before")
    @classmethod
    def validate_library_roots(cls, value: object) -> list[str]:
        return cls.parse_library_roots(value)

    @field_validator("exhentai_cookies", mode="before")
    @classmethod
    def parse_cookies(cls, value: object) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        parsed = json.loads(str(value))
        if not isinstance(parsed, dict):
            raise TypeError("EXHENTAI_COOKIES must be a JSON object")
        return {str(k): str(v) for k, v in parsed.items()}

    @field_validator("exhentai_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        host = (urlparse(value or "").hostname or "").lower()
        if host not in {"exhentai.org", "e-hentai.org"} and not host.endswith(
            (".exhentai.org", ".e-hentai.org")
        ):
            raise ValueError("exhentai_base_url must be on exhentai.org / e-hentai.org")
        return value

    @field_validator("telegram_chat_ids", "favorites_categories", mode="before")
    @classmethod
    def parse_list(cls, value: object) -> list[object]:
        if isinstance(value, list):
            return value
        if value is None or value == "":
            return []
        try:
            parsed = json.loads(str(value))
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            return [item.strip() for item in str(value).split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_proxy(self) -> "Settings":
        if self.http_proxy and self.socks5_proxy:
            raise ValueError("configure only one proxy")
        if self.download_quality not in {"original", "resample"}:
            raise ValueError("download_quality must be 'original' or 'resample'")
        if self.title_display not in {"japanese", "english", "directory"}:
            raise ValueError("title_display must be 'japanese', 'english', or 'directory'")
        if self.telegram_notify_level not in {"summary", "immediate", "failures_only", "off"}:
            raise ValueError(
                "telegram_notify_level must be 'summary', 'immediate', 'failures_only', or 'off'"
            )
        if self.telegram_notify_lang not in {"zh", "en"}:
            raise ValueError("telegram_notify_lang must be 'zh' or 'en'")
        if self.image_download_timeout_seconds < 1:
            raise ValueError("image_download_timeout_seconds must be >= 1")
        if self.image_slow_warmup_seconds < 1:
            raise ValueError("image_slow_warmup_seconds must be >= 1")
        if self.image_min_speed_kb_s < 1:
            raise ValueError("image_min_speed_kb_s must be >= 1")
        from .services.duplicate_resolver import DUPLICATE_POLICIES

        if self.duplicate_policy not in DUPLICATE_POLICIES:
            raise ValueError(f"duplicate_policy must be one of {', '.join(DUPLICATE_POLICIES)}")
        return self

    @classmethod
    def parse_library_roots(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        # Accept comma separated lists as well as one path per line (textarea).
        return [
            part.strip()
            for line in text.splitlines()
            for part in line.split(",")
            if part.strip()
        ]

    def model_post_init(self, __context: object, /) -> None:
        self.library_roots = self.parse_library_roots(self.library_roots)
        if not self.auth_secret:
            self.auth_secret = secrets.token_urlsafe(32)
            logger.warning("AUTH_SECRET is missing; using a temporary process secret")


def normalize_library_roots(value: object) -> list[str]:
    roots = Settings.parse_library_roots(value)
    result: list[str] = []
    seen: set[str] = set()
    for root in roots:
        normalized = str(Path(root).expanduser())
        key = str(Path(normalized).resolve(strict=False))
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def library_root_warnings(roots: list[str]) -> list[str]:
    return [
        f"Library root is missing or unreadable: {root}"
        for root in roots
        if not Path(root).exists() or not os.access(root, os.R_OK)
    ]


EDITABLE_SETTINGS = {
    "library_roots",
    "exhentai_base_url",
    "exhentai_cookies",
    "http_proxy",
    "socks5_proxy",
        "download_root",
        "download_concurrency",
        "page_concurrency",
        "download_quality",
        "use_hah",
        "image_download_timeout_seconds",
        "image_slow_warmup_seconds",
        "image_min_speed_kb_s",
        "title_display",
        "auto_sync_tags",
        "tag_sync_interval_seconds",
        "tag_sync_concurrency",
        "favorites_poll_interval_minutes",
    "favorites_categories",
    "download_favorites_enabled",
    "telegram_bot_token",
    "telegram_chat_ids",
    "telegram_allowed_user_ids",
    "telegram_notify_level",
    "telegram_notify_lang",
    "auth_required",
    "tag_translation_update_interval_minutes",
    "generate_thumbnails",
    "duplicate_policy",
}


def load_settings() -> Settings:
    """Load Settings from environment variables + built-in defaults.

    There is no config.json and no secrets file: everything user-editable is
    persisted in PostgreSQL (``app_config.user_settings``) and re-applied at
    startup.  Only infrastructure values that are needed to reach the database
    (``database_url``, ``log_level``, ``log_json``, ``scan_batch_size``) come
    from the environment, and they all have sensible defaults.
    """
    return Settings()


def get_settings() -> Settings:
    return load_settings()
