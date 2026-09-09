"""EhClient lease manager and fallback client adapter."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from ...logging import log_extra
from ..exceptions import EhClientUnavailableError

logger = logging.getLogger(__name__)


class EhClientManager:
    """Manages EhClient lifecycle, lease scopes, and temporary fallback client instances."""

    def __init__(
        self,
        client_getter: Callable[[], Any | None] | None = None,
        settings_getter: Callable[[], Any] | None = None,
        client_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._client_getter = client_getter
        self._settings_getter = settings_getter
        self._client_factory = client_factory
        self._active_client: Any | None = None
        self._active_generation: int = 0
        self._retiring_clients: set[Any] = set()

    @property
    def active_generation(self) -> int:
        """Monotonically increasing counter incremented on every client update."""
        return self._active_generation

    @property
    def retiring_clients(self) -> set[Any]:
        """Currently retiring client instances waiting for delayed drain."""
        return self._retiring_clients

    def update_client(self, new_client: Any) -> None:
        """Replace the active client and dispatch the previous client to delayed retirement."""
        old_client = self._active_client
        if old_client is None:
            old_client = self._get_active_client()

        self._active_client = new_client
        self._active_generation += 1

        if old_client is not None and old_client is not new_client:
            self.retire_client(old_client)

    def retire_client(self, client: Any, delay: float = 120.0) -> None:
        """Schedule a retired client to be safely closed after delay."""
        if client is None:
            return
        self._retiring_clients.add(client)

        async def _drain_and_close() -> None:
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                if hasattr(client, "aclose"):
                    await client.aclose()
                elif hasattr(client, "close"):
                    res = client.close()
                    if hasattr(res, "__await__"):
                        await res
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error closing retired EhClient",
                    extra=log_extra(error=str(exc)),
                )
            finally:
                self._retiring_clients.discard(client)

        try:
            from ..dependencies import spawn_task

            task = spawn_task(_drain_and_close(), "retire eh_client")
            if task is None:
                asyncio.create_task(_drain_and_close())
        except Exception:  # noqa: BLE001
            try:
                asyncio.create_task(_drain_and_close())
            except Exception:  # noqa: BLE001, S110
                pass

    def _get_active_client(self) -> Any | None:
        if self._active_client is not None:
            return self._active_client
        if self._client_getter is not None:
            return self._client_getter()
        try:
            from ..state import app_state

            return app_state.eh_client
        except Exception:  # noqa: BLE001
            return None

    def _get_settings(self) -> Any:
        if self._settings_getter is not None:
            return self._settings_getter()
        from ...config import get_settings
        from ..state import app_state

        if app_state.settings is not None:
            return app_state.settings
        return get_settings()

    def _create_temp_client(self, settings: Any) -> Any:
        if self._client_factory is not None:
            return self._client_factory(settings)
        from ...services.eh_client import EhClient

        return EhClient(settings)

    def is_configured(self) -> bool:
        """Check if E-Hentai credentials/cookies are configured."""
        try:
            settings = self._get_settings()
            cookie_path = getattr(settings, "eh_cookie_file", None) or getattr(settings, "exhentai_cookie_file", None)
            raw_cookie = getattr(settings, "exhentai_cookie", None) or getattr(settings, "eh_cookie", None)
            if raw_cookie or cookie_path:
                return True
        except Exception:  # noqa: BLE001, S110
            pass
        return False

    def get_client(self) -> Any:
        """Return the active persistent client or raise EhClientUnavailableError."""
        client = self._get_active_client()
        if client is not None:
            return client
        raise EhClientUnavailableError("Persistent EhClient is not initialized")

    @asynccontextmanager
    async def client_context(self) -> AsyncIterator[Any]:
        """Safely lease an EhClient.

        Yields the persistent EhClient if active; otherwise instantiates a temporary
        fallback client, ensuring proper lifecycle cleanup upon context exit.
        """
        active = self._get_active_client()
        if active is not None:
            yield active
            return

        settings = self._get_settings()
        try:
            temp_client = self._create_temp_client(settings)
        except Exception as exc:
            logger.error("Failed to instantiate temporary EhClient", extra=log_extra(error=str(exc)))
            raise EhClientUnavailableError(f"Could not initialize EhClient: {exc}") from exc

        try:
            if hasattr(temp_client, "__aenter__"):
                async with temp_client as client:
                    yield client
            else:
                try:
                    yield temp_client
                finally:
                    if hasattr(temp_client, "aclose"):
                        await temp_client.aclose()
                    elif hasattr(temp_client, "close"):
                        res = temp_client.close()
                        if hasattr(res, "__await__"):
                            await res
        except Exception as exc:
            if not isinstance(exc, EhClientUnavailableError):
                logger.debug("Error during EhClient context operation", extra=log_extra(error=str(exc)))
            raise
