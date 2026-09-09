"""Unified downloader test suite: execution, formats, resume, cancellation, speed budget, and pause handling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from galleryvault.app.state import app_state
from galleryvault.config import Settings, get_settings
from galleryvault.services import download_worker
from galleryvault.services.download_worker import run_download
from galleryvault.services.downloader import (
    Downloader,
    DownloadResult,
    DownloadTask,
    _existing_page_file,
)
from galleryvault.services.eh_client import (
    EhClient,
    EhClientError,
    EhImageSlowError,
    GalleryData,
    GalleryGoneError,
    GalleryPageData,
)
from galleryvault.services.settings_service import update_runtime_settings

VALID_JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20
VALID_WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20

# ==============================================================================
# 1. Page File Quality & Format Resolution
# ==============================================================================


def test_existing_page_file_respects_original_quality(tmp_path: Path) -> None:
    (tmp_path / "00000001.webp").write_bytes(VALID_WEBP_BYTES)

    assert _existing_page_file(tmp_path, 0, quality="original") is None
    assert _existing_page_file(tmp_path, 0, quality="ORIGINAL") is None

    assert _existing_page_file(tmp_path, 0, quality="resample") == tmp_path / "00000001.webp"
    assert _existing_page_file(tmp_path, 0) == tmp_path / "00000001.webp"

    (tmp_path / "00000001.jpg").write_bytes(VALID_JPG_BYTES)
    assert _existing_page_file(tmp_path, 0, quality="original") == tmp_path / "00000001.jpg"


class _CountingDownloaderClient:
    def __init__(self) -> None:
        self.image_calls: list[str] = []

    async def fetch_gallery(
        self,
        gid: int,
        token: str,
        max_pages: int | None = None,
        *,
        resolve_urls: bool = True,
    ) -> GalleryData:
        pages = [GalleryPageData(0, "p1_url", "tok1", "https://img.test/p1.jpg")]
        return GalleryData(gid, token, "test_gallery", pages)

    async def resolve_page(
        self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
    ) -> GalleryPageData:
        return GalleryPageData(
            page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
        )

    async def download_image(self, url: str) -> bytes:
        self.image_calls.append(url)
        return VALID_JPG_BYTES


@pytest.mark.asyncio
async def test_downloader_original_redownloads_when_only_webp_exists(tmp_path: Path) -> None:
    target_dir = tmp_path / "1-test_gallery"
    target_dir.mkdir()
    (target_dir / "00000001.webp").write_bytes(VALID_WEBP_BYTES)

    client = _CountingDownloaderClient()
    downloader = Downloader(client, tmp_path)
    task = DownloadTask(1, "tok", "test_gallery", quality="original")

    result = await downloader.execute(task)
    assert len(client.image_calls) == 1
    assert (result.path / "00000001.jpg").exists()


@pytest.mark.asyncio
async def test_downloader_original_skips_when_valid_jpg_exists(tmp_path: Path) -> None:
    target_dir = tmp_path / "1-test_gallery"
    target_dir.mkdir()
    (target_dir / "00000001.jpg").write_bytes(VALID_JPG_BYTES)

    client = _CountingDownloaderClient()
    downloader = Downloader(client, tmp_path)
    task = DownloadTask(1, "tok", "test_gallery", quality="original")

    result = await downloader.execute(task)
    assert len(client.image_calls) == 0
    assert (result.path / "00000001.jpg").exists()


# ==============================================================================
# 2. Downloader Core Execution, Retries & Magic Header Verification
# ==============================================================================


class FakeDownloadClient:
    def __init__(self) -> None:
        self.calls = 0
        self.last_max_pages = None

    async def fetch_gallery(
        self,
        gid: int,
        token: str,
        max_pages: int | None = None,
        *,
        resolve_urls: bool = True,
    ) -> GalleryData:
        self.calls += 1
        self.last_max_pages = max_pages
        if self.calls < 3:
            raise RuntimeError("temporary")
        pages = [GalleryPageData(0, "one", "p1"), GalleryPageData(1, "two", "p2")]
        if resolve_urls:
            pages = [
                GalleryPageData(p.index, p.url, p.token, f"https://img.test/{p.token}.jpg")
                for p in pages
            ]
        return GalleryData(gid, token, "safe/title", pages)

    async def resolve_page(
        self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
    ) -> GalleryPageData:
        return GalleryPageData(
            page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
        )

    async def download_image(self, url: str) -> bytes:
        return b"\xff\xd8\xff" + b"\x00" * 64


@pytest.mark.asyncio
async def test_downloader_retries_and_writes_version2(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    result = await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title"))
    assert client.calls == 3
    metadata = (result.path / ".ehviewer").read_text().splitlines()
    assert metadata[1:8] == ["00000000", "1", "tok", "1", "1", "20", "2"]
    assert (result.path / ".ehviewer").read_text().splitlines()[-2:] == ["0 p1", "1 p2"]
    assert sorted(p.name for p in result.path.glob("*.jpg")) == ["00000001.jpg", "00000002.jpg"]
    assert "/" not in result.path.name


@pytest.mark.asyncio
async def test_downloader_passes_max_pages_to_fetch_gallery(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    client.calls = 3
    await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title", max_pages=1))
    assert client.last_max_pages == 1


@pytest.mark.asyncio
async def test_downloader_reports_progress(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    client.calls = 3
    progress: list[tuple[int, int]] = []

    async def on_progress(current: int, total: int) -> None:
        progress.append((current, total))

    await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title"), progress=on_progress)
    assert (0, 2) in progress
    assert (2, 2) in progress
    assert progress[0] == (0, 2) and progress[-1] == (2, 2)


@pytest.mark.asyncio
async def test_downloader_speed_stats() -> None:
    client = FakeDownloadClient()
    client.calls = 3
    downloader = Downloader(client, "/tmp/gv-speed-test")
    await downloader._record_bytes(42, 2048, 1)
    await asyncio.sleep(0.05)
    stats = await downloader.speed_stats(42, current_page=1, total_pages=10)
    assert stats is not None
    assert stats["speed"] > 0
    assert stats["eta_seconds"] > 0
    assert await downloader.speed_stats(999) is None
    downloader._clear_stats(42)
    assert await downloader.speed_stats(42) is None


class CountingDownloadClient(FakeDownloadClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 3
        self.image_calls = 0

    async def download_image(self, url: str) -> bytes:
        self.image_calls += 1
        return await super().download_image(url)


@pytest.mark.asyncio
async def test_downloader_resumes_without_refetching_existing_pages(tmp_path: Path) -> None:
    client = CountingDownloadClient()
    downloader = Downloader(client, tmp_path)
    await downloader.execute(DownloadTask(1, "tok", "title"))
    assert client.image_calls == 2
    result2 = await downloader.execute(DownloadTask(1, "tok", "title"))
    assert client.image_calls == 2
    assert (result2.path / "00000001.jpg").exists()
    assert (result2.path / "00000002.jpg").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_payload",
    [
        b"",
        b"<html>error page</html>",
        b"<!DOCTYPE html><html><body>Error</body></html>",
        b"\x00" * 32,
        b"random junk data without image magic header",
    ],
)
async def test_downloader_rejects_invalid_magic_and_html(
    tmp_path: Path, bad_payload: bytes
) -> None:
    class BadImageClient(FakeDownloadClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 3

        async def download_image(self, url: str) -> bytes:
            return bad_payload

    client = BadImageClient()
    downloader = Downloader(client, tmp_path)
    with pytest.raises(ValueError, match="image response is invalid"):
        await downloader.execute(DownloadTask(1, "tok", "title", id=9))
    target_dir = tmp_path / "1-title"
    if target_dir.exists():
        assert list(target_dir.glob("*.jpg")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "valid_header",
    [
        b"RIFF" + b"\x00" * 20,
        b"\xff\xd8\xff" + b"\x00" * 20,
        b"\x89PNG" + b"\x00" * 20,
        b"GIF8" + b"\x00" * 20,
    ],
)
async def test_downloader_accepts_valid_magics(tmp_path: Path, valid_header: bytes) -> None:
    class ValidMagicClient(FakeDownloadClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 3

        async def download_image(self, url: str) -> bytes:
            return valid_header

    client = ValidMagicClient()
    result = await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title"))
    assert result.pages == 2


@pytest.mark.asyncio
async def test_downloader_does_not_skip_corrupt_existing_page(tmp_path: Path) -> None:
    target_dir = tmp_path / "1-title"
    target_dir.mkdir(parents=True)
    corrupt_page = target_dir / "00000001.jpg"
    corrupt_page.write_bytes(b"corrupted data that should be re-downloaded")

    client = CountingDownloadClient()
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(DownloadTask(1, "tok", "title"))
    assert client.image_calls == 2
    assert (result.path / "00000001.jpg").read_bytes().startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
async def test_downloader_reuses_existing_gid_directory(tmp_path: Path) -> None:
    existing_dir = tmp_path / "1-original_name"
    existing_dir.mkdir(parents=True)
    (existing_dir / "00000001.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)

    client = CountingDownloadClient()
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(DownloadTask(1, "tok", "completely_different_name"))
    assert result.path == existing_dir
    assert client.image_calls == 1


@pytest.mark.asyncio
async def test_downloader_uses_download_title_setting(tmp_path: Path) -> None:
    class JpnDownloadClient(FakeDownloadClient):
        async def fetch_gallery(self, gid: int, token: str, max_pages: int | None = None, *, resolve_urls: bool = True) -> GalleryData:
            self.calls += 1
            pages = [GalleryPageData(0, "one", "p1")]
            if resolve_urls:
                pages = [GalleryPageData(0, "one", "p1", "https://img.test/p1.jpg")]
            return GalleryData(gid, token, "Latin Title", pages, title_jpn="Japanese Title")

    client = JpnDownloadClient()
    client.calls = 3
    client.settings = SimpleNamespace(download_title="title_jpn")
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(DownloadTask(1, "tok", "Latin Title"))
    assert "Japanese Title" in result.path.name


# ==============================================================================
# 3. Downloader Resilience, 403 Healing, 509 Abort & Skip-H@H
# ==============================================================================


@pytest.mark.asyncio
async def test_persistent_downloader_does_not_retry_inside_downloader(tmp_path: Path) -> None:
    client = FakeDownloadClient()
    with pytest.raises(RuntimeError):
        await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title", id=9))
    assert client.calls == 1


class FlakyDownloadClient(FakeDownloadClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 3
        self.image_attempts = 0
        self.resolve_calls = 0

    async def resolve_page(
        self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
    ) -> GalleryPageData:
        self.resolve_calls += 1
        return GalleryPageData(
            page.index,
            page.url,
            page.token,
            f"https://img.test/{page.token}.jpg?v={self.resolve_calls}",
        )

    async def download_image(self, url: str) -> bytes:
        self.image_attempts += 1
        if self.image_attempts == 1:
            raise EhClientError("ExHentai authentication is required or expired")
        return await super().download_image(url)


@pytest.mark.asyncio
async def test_downloader_self_heals_403_by_re_resolving_url(tmp_path: Path) -> None:
    client = FlakyDownloadClient()
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(DownloadTask(1, "tok", "title"))
    assert client.image_attempts == 3
    assert client.resolve_calls >= 2
    assert sorted(p.name for p in result.path.glob("*.jpg")) == ["00000001.jpg", "00000002.jpg"]


class AlwaysFailDownloadClient(FakeDownloadClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 3

    async def resolve_page(
        self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
    ) -> GalleryPageData:
        return GalleryPageData(
            page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
        )

    async def download_image(self, url: str) -> bytes:
        raise EhClientError("ExHentai image download failed")


@pytest.mark.asyncio
async def test_downloader_escalates_after_five_page_attempts(tmp_path: Path) -> None:
    client = AlwaysFailDownloadClient()
    with pytest.raises(EhClientError, match="image download failed"):
        await Downloader(client, tmp_path).execute(DownloadTask(1, "tok", "title", id=9))


@pytest.mark.asyncio
async def test_downloader_retries_with_skip_hath(tmp_path: Path) -> None:
    class RetryTrackingClient(FakeDownloadClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 3
            self.skip_hath_flags: list[bool] = []
            self.download_attempts = 0

        async def resolve_page(
            self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
        ) -> GalleryPageData:
            self.skip_hath_flags.append(skip_hath)
            return GalleryPageData(
                page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
            )

        async def download_image(self, url: str) -> bytes:
            self.download_attempts += 1
            if self.download_attempts == 1:
                return b"invalid data"
            return b"\xff\xd8\xff" + b"\x00" * 64

    client = RetryTrackingClient()
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(DownloadTask(1, "tok", "title"))
    assert result.pages == 2
    assert client.skip_hath_flags[0] is False
    assert True in client.skip_hath_flags


@pytest.mark.asyncio
async def test_downloader_aborts_immediately_on_509_placeholder(tmp_path: Path) -> None:
    class RateLimitedClient(FakeDownloadClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 3
            self.skip_hath_flags: list[bool] = []

        async def fetch_gallery(
            self,
            gid: int,
            token: str,
            max_pages: int | None = None,
            *,
            resolve_urls: bool = True,
        ) -> GalleryData:
            self.calls = 3
            pages = [GalleryPageData(0, "one", "p1")]
            return GalleryData(gid, token, "safe/title", pages)

        async def resolve_page(
            self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
        ) -> GalleryPageData:
            self.skip_hath_flags.append(skip_hath)
            return GalleryPageData(
                page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
            )

        async def download_image(self, url: str) -> bytes:
            raise EhImageSlowError("ExHentai rate limited (509 placeholder)")

    client = RateLimitedClient()
    downloader = Downloader(client, tmp_path)
    with pytest.raises(EhImageSlowError, match="509 placeholder"):
        await downloader.execute(DownloadTask(1, "tok", "title", id=9))
    assert client.skip_hath_flags == [False]


@pytest.mark.asyncio
async def test_downloader_retries_with_skip_hath_on_throttled_node(tmp_path: Path) -> None:
    class ThrottledRetryClient(FakeDownloadClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 3
            self.skip_hath_flags: list[bool] = []
            self.download_attempts = 0

        async def fetch_gallery(
            self,
            gid: int,
            token: str,
            max_pages: int | None = None,
            *,
            resolve_urls: bool = True,
        ) -> GalleryData:
            self.calls = 3
            pages = [GalleryPageData(0, "one", "p1")]
            return GalleryData(gid, token, "safe/title", pages)

        async def resolve_page(
            self, gid: int, page: GalleryPageData, showkey: Any = None, *, skip_hath: bool = False
        ) -> GalleryPageData:
            self.skip_hath_flags.append(skip_hath)
            return GalleryPageData(
                page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
            )

        async def download_image(self, url: str) -> bytes:
            self.download_attempts += 1
            if self.download_attempts == 1:
                raise EhImageSlowError("H@H node throttled (5 KB/s < 10 KB/s)")
            return b"\xff\xd8\xff" + b"\x00" * 64

    client = ThrottledRetryClient()
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(DownloadTask(1, "tok", "title"))
    assert result.pages == 1
    assert client.skip_hath_flags == [False, True]


# ==============================================================================
# 4. Image Downloading Stream, Speed Budget & Content-Length
# ==============================================================================


@pytest.mark.asyncio
async def test_download_image_streams_with_content_length_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\xff\xd8\xff" + b"x" * 500, headers={"content-type": "image/jpeg"}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        eh = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=client)
        data, ctype = await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")
        assert data.startswith(b"\xff\xd8\xff") and ctype == "image/jpeg"


@pytest.mark.asyncio
async def test_download_image_rejects_truncated_and_hijacked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "redirect.jpg" in request.url.path:
            return httpx.Response(302, headers={"location": "https://evil.example/x.jpg"})
        if request.url.host == "evil.example":
            return httpx.Response(200, content=b"\xff\xd8\xff" + b"y" * 100)
        return httpx.Response(
            200,
            content=b"\xff\xd8\xff" + b"x" * 7,
            headers={"content-type": "image/jpeg", "content-length": "500"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        eh = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=client)
        with pytest.raises(EhClientError, match="redirected to unexpected host"):
            await eh.download_image_with_metadata("https://node.hath.network/h/redirect.jpg")
        with pytest.raises(EhClientError, match="incomplete"):
            await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")


@pytest.mark.asyncio
async def test_download_image_request_error_includes_host_and_error_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        eh = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=client)
        with pytest.raises(
            EhClientError,
            match=r"ExHentai image download failed: ConnectError on node\.hath\.network",
        ):
            await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")


class _TrickleStream(httpx.AsyncByteStream):
    def __init__(self, chunks: int = 4, chunk_size: int = 32, delay: float = 0.1) -> None:
        self._chunks, self._chunk_size, self._delay = chunks, chunk_size, delay

    async def __aiter__(self) -> Any:
        for _ in range(self._chunks):
            await asyncio.sleep(self._delay)
            yield b"x" * self._chunk_size


@pytest.mark.asyncio
async def test_download_image_aborts_on_throttled_hah_node() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=_TrickleStream(chunks=15, chunk_size=32, delay=0.1),
            headers={"content-type": "image/jpeg"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        eh = EhClient(
            Settings(
                exhentai_base_url="https://exhentai.org",
                image_slow_warmup_seconds=1,
                image_download_timeout_seconds=60,
                image_min_speed_kb_s=100000,
            ),
            client=client,
        )
        with pytest.raises(EhImageSlowError, match="throttled"):
            await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")


@pytest.mark.asyncio
async def test_download_image_aborts_on_total_time_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=_TrickleStream(chunks=5, chunk_size=10 * 1024, delay=0.6),
            headers={"content-type": "image/jpeg"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        eh = EhClient(
            Settings(
                exhentai_base_url="https://exhentai.org",
                image_slow_warmup_seconds=2,
                image_download_timeout_seconds=1,
                image_min_speed_kb_s=1,
            ),
            client=client,
        )
        with pytest.raises(EhImageSlowError, match="budget"):
            await eh.download_image_with_metadata("https://node.hath.network/h/x.jpg")


@pytest.mark.asyncio
async def test_download_image_rejects_509_placeholder_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be sent for a 509 placeholder URL")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        eh = EhClient(Settings(exhentai_base_url="https://exhentai.org"), client=client)
        with pytest.raises(EhImageSlowError, match="509"):
            await eh.download_image_with_metadata("https://node.hath.network/509.gif")


# ==============================================================================
# 5. Cancellation Race Conditions & Worker Status
# ==============================================================================


class _CancelRow:
    def __init__(self, task_id: int) -> None:
        self.id = task_id
        self.gid = 7
        self.token = "token"
        self.status = "downloading"
        self.retry_count = 0
        self.max_retries = 10
        self.target_path = None
        self.category = None
        self.error_message = None
        self.retry_at = None
        self.finished_at = None
        self.started_at = None


class _CancelSession:
    def __init__(self, row_provider: Any) -> None:
        self._provider = row_provider
        self.attempts: list[tuple[int, int, str]] = []
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    def begin(self) -> _CancelSession:
        return self

    async def get(self, model: Any, pk: Any) -> Any:
        row = self._provider()
        row.id = pk
        return row

    def add(self, obj: Any) -> None:
        self.attempts.append((obj.task_id, obj.attempt, obj.status))

    async def flush(self) -> None:
        pass


class _CancelDownloader:
    root = None

    def __init__(self, result: Any, cancel_between: bool = False) -> None:
        self.result = result
        self.cancel_between = cancel_between
        self.cancelled_now = False

    async def execute(self, task: Any, *, progress: Any = None, **_: Any) -> Any:
        if self.cancel_between:
            self.cancelled_now = True
            app_state.task_manager.request_cancel(task.id)
        return self.result


class _CancelSettings:
    def __init__(self, root: Path) -> None:
        self.download_root = str(root)
        self.telegram_notify_level = "always"


def _patch_cancel_context(monkeypatch: pytest.MonkeyPatch, *, row_provider: Any, downloader: Any) -> list[Any]:
    monkeypatch.setattr(app_state, "session_factory", lambda: _CancelSession(row_provider))
    monkeypatch.setattr(app_state, "downloader", downloader)
    monkeypatch.setattr(app_state, "settings", _CancelSettings(Path("/tmp")))
    monkeypatch.setattr(download_worker, "maybe_scan_after_download", lambda result: None)
    notifications: list[tuple[str, object, object]] = []

    async def record_notification(kind: str, title: Any, detail: Any = None) -> None:
        notifications.append((kind, title, detail))

    monkeypatch.setattr(download_worker, "record_download_notification", record_notification)
    return notifications


@pytest.mark.asyncio
async def test_cancel_lands_after_download_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _CancelRow(42)
    phase = [0]

    def row_provider() -> _CancelRow:
        phase[0] += 1
        if phase[0] >= 2:
            row.status = "cancelled"
        return row

    result = DownloadResult(gid=7, path=Path("/tmp/dl"), pages=5, category="manga", title="t")
    notifications = _patch_cancel_context(
        monkeypatch,
        row_provider=row_provider,
        downloader=_CancelDownloader(result, cancel_between=True),
    )

    await run_download(DownloadTask(7, "token", "t", id=42))
    assert row.status == "cancelled"
    assert not app_state.task_manager.is_cancelled(42)
    assert notifications == []


@pytest.mark.asyncio
async def test_cancel_via_db_status_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _CancelRow(43)
    phase = [0]

    def row_provider() -> _CancelRow:
        phase[0] += 1
        if phase[0] >= 2:
            row.status = "cancelled"
        return row

    result = DownloadResult(gid=7, path=Path("/tmp/dl"), pages=5, category="manga", title="t")
    notifications = _patch_cancel_context(
        monkeypatch,
        row_provider=row_provider,
        downloader=_CancelDownloader(result),
    )

    await run_download(DownloadTask(7, "token", "t", id=43))
    assert row.status == "cancelled"
    assert not app_state.task_manager.is_cancelled(43)
    assert notifications == []


@pytest.mark.asyncio
async def test_success_path_when_no_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _CancelRow(44)
    result = DownloadResult(gid=7, path=Path("/tmp/dl"), pages=5, category="manga", title="t")
    notifications = _patch_cancel_context(
        monkeypatch,
        row_provider=lambda: row,
        downloader=_CancelDownloader(result),
    )

    await run_download(DownloadTask(7, "token", "t", id=44))
    assert row.status == "success"
    assert row.target_path == "/tmp/dl"
    assert row.retry_count == 0
    assert notifications == [("ok", "t", "5")]


@pytest.mark.asyncio
async def test_gallery_gone_error_marks_failed_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingDownloader:
        root = None

        async def execute(self, task: Any, *, progress: Any = None, **_: Any) -> None:
            raise GalleryGoneError("gallery does not exist on ExHentai (404)")

    row = _CancelRow(45)
    notifications = _patch_cancel_context(
        monkeypatch,
        row_provider=lambda: row,
        downloader=_FailingDownloader(),
    )

    await run_download(DownloadTask(7, "token", "t", id=45))
    assert row.status == "failed"
    assert row.retry_at is None
    assert row.retry_count >= row.max_retries
    assert "deleted or not found" in (row.error_message or "")
    assert len(notifications) == 1
    assert notifications[0][0] == "fail"


@pytest.mark.asyncio
async def test_cancel_pending_task_arms_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import downloads as dl_router
    from galleryvault.app.routers.downloads import cancel_download

    row = _CancelRow(99)
    row.status = "pending"

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def begin(self) -> FakeSession:
            return self

        async def get(self, model: Any, pk: Any) -> Any:
            return row

    class FakeRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def cancel(self, task_id: int) -> bool:
            row.status = "cancelled"
            return True

    async def fake_get_session() -> Any:
        yield FakeSession()

    monkeypatch.setattr(dl_router, "get_session", fake_get_session)
    monkeypatch.setattr(dl_router, "DownloadRepository", FakeRepo)

    res = await cancel_download(99)
    assert res == {"id": 99, "status": "cancelled"}
    assert app_state.task_manager.is_cancelled(99)
    app_state.task_manager.clear_cancelled(99)


@pytest.mark.asyncio
async def test_worker_pending_cancelled_task_skips_download(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _CancelRow(101)
    row.status = "pending"
    app_state.task_manager.request_cancel(101)

    executed: list[bool] = []

    class _TrackingDownloader:
        root = None

        async def execute(self, *args: Any, **kwargs: Any) -> None:
            executed.append(True)
            raise AssertionError("execute should not be called")

    notifications = _patch_cancel_context(
        monkeypatch,
        row_provider=lambda: row,
        downloader=_TrackingDownloader(),
    )

    await run_download(DownloadTask(7, "token", "t", id=101))
    assert executed == []
    assert row.status == "cancelled"
    assert not app_state.task_manager.is_cancelled(101)
    assert notifications == []


# ==============================================================================
# 6. Pause Settings & State Handling
# ==============================================================================


@pytest.mark.asyncio
async def test_pause_save_merges_not_overwrites(monkeypatch: pytest.MonkeyPatch) -> None:
    from galleryvault.app.routers import tasks as tasks_module

    base = get_settings().model_copy(
        update={
            "exhentai_cookies": {"ipb_member_id": "1", "ipb_pass_hash": "h", "igneous": "i"},
            "library_roots": ["/library"],
            "global_paused": False,
        }
    )
    app_state.settings = base

    stored = {
        "exhentai_cookies": {"ipb_member_id": "1"},
        "library_roots": ["/library"],
        "some_other": "keep",
    }

    class FakeRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def get(self) -> dict[str, Any]:
            return dict(stored)

        async def save(self, value: dict[str, Any]) -> None:
            stored.clear()
            stored.update(value)

    monkeypatch.setattr(tasks_module, "SettingsRepository", FakeRepo)

    class FakeSession:
        def begin(self) -> FakeSession:
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

    async def fake_get_session() -> Any:
        yield FakeSession()

    monkeypatch.setattr(tasks_module, "get_session", fake_get_session)
    orig_factory = app_state.session_factory
    app_state.session_factory = lambda: FakeSession()
    try:
        update_runtime_settings({"global_paused": True})
        assert app_state.settings.global_paused is True

        result = await tasks_module.set_pause({"paused": True})
        assert result["paused"] is True
        assert stored.get("exhentai_cookies") == {"ipb_member_id": "1"}
        assert stored.get("library_roots") == ["/library"]
        assert stored.get("some_other") == "keep"
        assert stored.get("global_paused") is True
        assert app_state.settings.global_paused is True
    finally:
        app_state.session_factory = orig_factory


def test_update_runtime_settings_allows_global_paused() -> None:
    base = get_settings().model_copy(update={"global_paused": False})
    app_state.settings = base
    update_runtime_settings({"global_paused": True})
    assert app_state.settings.global_paused is True
    update_runtime_settings({"global_paused": False})
    assert app_state.settings.global_paused is False


@pytest.mark.asyncio
async def test_downloader_rejects_truncated_jpeg_above_threshold(tmp_path: Path) -> None:
    class TruncatedJpegClient(FakeDownloadClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 3

        async def download_image(self, url: str) -> bytes:
            return b"\xff\xd8\xff\xe0" + b"\x00" * 600

    client = TruncatedJpegClient()
    downloader = Downloader(client, tmp_path)
    with pytest.raises(RuntimeError) as exc_info:
        await downloader.execute(DownloadTask(1, "tok", "title"))
    assert "image integrity check failed" in str(exc_info.value.__cause__)

