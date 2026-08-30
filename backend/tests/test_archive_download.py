"""Tests for the ExHentai archive (zip) download channel.

Covers the archiver.php parser, the executor's full unzip->rename->metadata
flow, the GP funds gate, and the idempotent resume (persisted zip URL).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from galleryvault.services.downloader import (
    ArchiveNotRetryableError,
    Downloader,
    DownloadTask,
)
from galleryvault.services.eh_client import (
    ArchiveInfo,
    EhClientError,
    GalleryData,
    GalleryPageData,
    _parse_archive_cost,
    _parse_archive_info,
    _parse_archive_size,
)

ARCHIVER_PAGE = """<html><body>
<div id="db">
    <h1 style="font-size:10pt; font-weight:bold">COSPLAYTALE</h1>
    <div style="font-weight:bold">You have <b style="color:#1a1a1a">1,250</b> GP</div>
    <div style="width:180px; float:left">
        <div style="text-align:center; margin-top:4px">Download Cost: &nbsp;
            <strong>Free!</strong></div>
        <form action="https://exhentai.org/archiver.php?gid=2881867&amp;token=b57&amp;or=key"
              method="post">
            <input type="hidden" name="dltype" value="org"/>
            <div style="margin:3px auto"><input type="submit" name="dlcheck"
                                                value="Download Original Archive"
                                                style="width:180px"/></div>
        </form>
        <p>Estimated Size: &nbsp; <strong>18.46 MiB</strong></p>
    </div>
    <div style="width:180px; float:right">
        <div style="text-align:center; margin-top:4px">Download Cost: &nbsp;
            <strong>Free!</strong></div>
        <form action="https://exhentai.org/archiver.php?gid=2881867&amp;token=b57&amp;or=key"
              method="post">
            <input type="hidden" name="dltype" value="res"/>
            <div style="margin:3px auto"><input type="submit" name="dlcheck"
                                                value="Download Resample Archive"
                                                style="width:180px"/></div>
        </form>
        <p>Estimated Size: &nbsp; <strong>2.17 MiB</strong></p>
    </div>
</div>
</body></html>"""


def test_parse_archive_cost_and_size() -> None:
    assert _parse_archive_cost("Free!") == 0
    assert _parse_archive_cost("1,250") == 1250
    assert _parse_archive_cost("N/A") == 0
    assert _parse_archive_size("18.46 MiB") == int(18.46 * 1024**2)
    assert _parse_archive_size("2.17 MiB") == int(2.17 * 1024**2)
    assert _parse_archive_size("N/A") == 0


def test_parse_archive_info_page() -> None:
    info = _parse_archive_info(ARCHIVER_PAGE)
    assert info.funds == 1250
    assert info.original_cost == 0 and info.resample_cost == 0
    assert info.original_size == int(18.46 * 1024**2)
    assert info.resample_size == int(2.17 * 1024**2)
    assert "or=key" in (info.original_url or "")
    assert info.original_url == info.resample_url


def test_parse_archive_info_without_balance_does_not_misread_cost() -> None:
    """A page with no ``You have X GP`` row (current ExHentai layout) must not
    treat the ``Download Cost`` labels as the balance."""
    info = _parse_archive_info(ARCHIVER_PAGE.replace("You have <b style=\"color:#1a1a1a\">1,250</b> GP", ""))
    assert info.funds is None
    assert info.original_cost == 0 and info.original_size == int(18.46 * 1024**2)


def test_parse_gp_balance_kpg() -> None:
    from galleryvault.services.eh_client import ARCHIVE_GP_BALANCE_RE

    page = """<div style="margin-top:5px; font-weight:bold">Available: 288,429 kGP</div>"""
    match = ARCHIVE_GP_BALANCE_RE.search(page)
    assert match is not None
    assert int(float(match.group(1).replace(",", "")) * 1000) == 288_429_000


def test_parse_archive_info_unavailable_tier() -> None:
    """A tier with ``N/A`` cost/size must parse without crashing and mark its
    URL as unavailable so it is never charged or downloaded."""
    page = """<html><body>
    <div style="font-weight:bold">You have <b style="color:#1a1a1a">1,250</b> GP</div>
    <div style="width:180px; float:left">
        <div style="text-align:center; margin-top:4px">Download Cost: &nbsp;
            <strong>59,782 GP</strong></div>
        <form action="https://exhentai.org/archiver.php?gid=3188703&amp;token=t&amp;or=key"
              method="post">
            <input type="hidden" name="dltype" value="org"/>
            <div style="margin:3px auto"><input type="submit" name="dlcheck"
                                                value="Download Original Archive"
                                                style="width:180px"/></div>
        </form>
        <p>Estimated Size: &nbsp; <strong>2.78 GiB</strong></p>
    </div>
    <div style="width:180px; float:right">
        <div style="text-align:center; margin-top:4px">Download Cost: &nbsp;
            <strong>N/A</strong></div>
        <form action="https://exhentai.org/archiver.php?gid=3188703&amp;token=t&amp;or=key"
              method="post">
            <input type="hidden" name="dltype" value="res"/>
            <div style="margin:3px auto"><input type="submit" name="dlcheck"
                                                value="Download Resample Archive"
                                                disabled="disabled"/></div>
        </form>
        <p>Estimated Size: &nbsp; <strong>N/A</strong></p>
    </div>
</body></html>"""
    info = _parse_archive_info(page)
    assert info.funds == 1250
    assert info.original_url is not None
    assert info.resample_url is None
    assert info.resample_size == 0
    assert info.resample_cost == 0
    assert "or=key" in (info.original_url or "")


def _make_zip(images: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in images:
            archive.writestr(name, data)
    return buffer.getvalue()


class FakeArchiveClient:
    settings = SimpleNamespace(
        download_quality="resample", download_title="japanese"
    )

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.download_calls = 0

    async def fetch_gallery(
        self, gid, token, max_pages=None, *, resolve_urls=True
    ) -> GalleryData:
        pages = [
            GalleryPageData(i, f"https://exhentai.org/s/x/{gid}-{i}", f"tok{i}")
            for i in range(3)
        ]
        return GalleryData(
            int(gid), token, "Arc Title", pages, [{"namespace": "artist", "name": "a"}],
            "manga", "アーカイブ",
        )

    async def fetch_archive_info(self, gid: int, token: str) -> ArchiveInfo:
        return ArchiveInfo(
            funds=1000,
            original_cost=100,
            original_size=1024 * 1024,
            original_url="https://exhentai.org/archiver.php?gid=1&token=t&or=key",
            resample_cost=10,
            resample_size=512 * 1024,
            resample_url="https://exhentai.org/archiver.php?gid=1&token=t&or=key",
        )

    async def request_archive(self, url: str, dltype: str) -> str:
        self.requests.append((url, dltype))
        return "https://exhentai.org/dl/archive.zip"

    async def download_archive(self, url: str, dest: Path, cb=None) -> int:
        data = _make_zip(
            [
                ("b.jpg", b"\xff\xd8\xffb"),
                ("a.png", b"\x89PNG a"),
                ("c.gif", b"GIF89a c"),
            ]
        )
        dest.write_bytes(data)
        if cb is not None:
            await cb(len(data), len(data))
        return len(data)

    async def resolve_page(self, gid, page, showkey=None) -> GalleryPageData:
        return page

    async def download_image_with_metadata(self, url: str) -> tuple[bytes, str]:
        return b"\xff\xd8\xff" + b"\x00" * 64, "image/jpeg"


@pytest.mark.asyncio
async def test_archive_downloader_writes_renamed_gallery(tmp_path: Path) -> None:
    client = FakeArchiveClient()
    result = await Downloader(client, tmp_path).execute(
        DownloadTask(1, "t", "title", mode="archive", quality="resample")
    )
    assert client.requests == [
        ("https://exhentai.org/archiver.php?gid=1&token=t&or=key", "res")
    ]
    # Renaming follows the archive's sorted filename order: a.png -> 1, b.jpg -> 2,
    # c.gif -> 3.
    assert sorted(p.name for p in result.path.glob("*.jpg")) == ["00000002.jpg"]
    assert sorted(p.name for p in result.path.glob("*.png")) == ["00000001.png"]
    assert sorted(p.name for p in result.path.glob("*.gif")) == ["00000003.gif"]
    metadata = (result.path / ".ehviewer").read_text().splitlines()
    assert metadata[:8] == ["VERSION2", "00000000", "1", "t", "1", "1", "20", "3"]
    assert metadata[-3:] == ["0 tok0", "1 tok1", "2 tok2"]
    assert not (result.path / ".archive.json").exists()
    assert not (result.path / "archive.zip").exists()


@pytest.mark.asyncio
async def test_archive_downloader_records_speed_stats(tmp_path: Path) -> None:
    """Archive downloads must feed the live speed/ETA stats so the tasks UI
    shows a speed (the page-by-page path does via _record_bytes; the archive
    zip path used to skip it entirely)."""
    client = FakeArchiveClient()
    downloader = Downloader(client, tmp_path)
    recorded: list[tuple[int, int]] = []

    async def spy(gid: int, count: int, done: int) -> None:
        recorded.append((count, done))

    downloader._record_bytes = spy  # type: ignore[method-assign]
    await downloader.execute(
        DownloadTask(1, "t", "title", mode="archive", quality="resample")
    )
    assert recorded, "_record_bytes was never called for the archive download"
    assert all(bytes_count > 0 for bytes_count, _ in recorded)


@pytest.mark.asyncio
async def test_archive_original_tier_passes_org_dltype(tmp_path: Path) -> None:
    client = FakeArchiveClient()
    await Downloader(client, tmp_path).execute(
        DownloadTask(1, "t", "title", mode="archive", quality="original")
    )
    assert client.requests[0][1] == "org"


@pytest.mark.asyncio
async def test_archive_insufficient_funds_is_not_retryable(tmp_path: Path) -> None:
    """With fallback disabled, insufficient GP still fails the task with
    ArchiveNotRetryableError (never burns the retry budget on a non-healing
    condition)."""

    class PoorClient(FakeArchiveClient):
        settings = SimpleNamespace(
            download_quality="resample",
            download_title="japanese",
            archive_fallback_pages=False,
        )

        async def fetch_archive_info(self, gid: int, token: str) -> ArchiveInfo:
            return ArchiveInfo(
                funds=5,
                original_cost=100,
                original_size=0,
                original_url=None,
                resample_cost=10,
                resample_size=0,
                resample_url=None,
            )

    client = PoorClient()
    with pytest.raises(ArchiveNotRetryableError):
        await Downloader(client, tmp_path).execute(
            DownloadTask(1, "t", "title", id=1, mode="archive", quality="resample")
        )
    assert client.requests == []


@pytest.mark.asyncio
async def test_archive_resume_keeps_zip_url(tmp_path: Path) -> None:
    """A failed transfer must not re-request the archive on the next attempt."""

    class FlakyClient(FakeArchiveClient):
        def __init__(self) -> None:
            super().__init__()
            self._failed = False

        async def download_archive(self, url: str, dest: Path, cb=None) -> int:
            self.download_calls += 1
            if not self._failed:
                self._failed = True
                dest.write_bytes(b"\x50\x4b" + b"\x00" * 32)  # partial zip
                raise EhClientError("ExHentai archive download failed")
            return await super().download_archive(url, dest, cb)

    client = FlakyClient()
    downloader = Downloader(client, tmp_path)
    with pytest.raises(EhClientError):
        await downloader.execute(
            DownloadTask(1, "t", "title", id=1, mode="archive", quality="resample")
        )
    # The persisted zip URL survives the failed attempt…
    state_file = tmp_path / ".gv-1" / ".archive.json"
    assert state_file.exists()
    assert client.requests == [("https://exhentai.org/archiver.php?gid=1&token=t&or=key", "res")]
    # …so a retry resumes the zip instead of charging GP a second time.
    result = await downloader.execute(
        DownloadTask(1, "t", "title", id=1, mode="archive", quality="resample")
    )
    assert client.download_calls == 2
    assert len(client.requests) == 1
    assert (result.path / "00000001.png").exists()


@pytest.mark.asyncio
async def test_archive_unavailable_tier_falls_back_to_pages(tmp_path: Path) -> None:
    """A gallery whose requested archive tier is unavailable (resample N/A)
    falls back to the page-by-page channel when archive_fallback_pages is on,
    instead of failing the whole download."""

    class NoResampleClient(FakeArchiveClient):
        async def fetch_archive_info(self, gid: int, token: str) -> ArchiveInfo:
            return ArchiveInfo(
                funds=1000,
                original_cost=100,
                original_size=1024 * 1024,
                original_url="https://exhentai.org/archiver.php?gid=1&token=t&or=key",
                resample_cost=0,
                resample_size=0,
                resample_url=None,
            )

    client = NoResampleClient()
    downloader = Downloader(client, tmp_path)
    result = await downloader.execute(
        DownloadTask(1, "t", "title", mode="archive", quality="resample")
    )
    # No archive was ever requested; the gallery came down page-by-page.
    assert client.requests == []
    assert result.pages == 3
    assert sorted(p.name for p in result.path.glob("*.jpg")) == [
        "00000001.jpg",
        "00000002.jpg",
        "00000003.jpg",
    ]
    assert not (tmp_path / ".gv-1").exists()


@pytest.mark.asyncio
async def test_archive_fallback_disabled_keeps_failure(tmp_path: Path) -> None:
    """With archive_fallback_pages off, an unavailable archive tier still
    fails the task with ArchiveNotRetryableError."""

    class NoResampleClient(FakeArchiveClient):
        settings = SimpleNamespace(
            download_quality="resample",
            download_title="japanese",
            archive_fallback_pages=False,
        )

        async def fetch_archive_info(self, gid: int, token: str) -> ArchiveInfo:
            return ArchiveInfo(
                funds=1000,
                original_cost=100,
                original_size=1024 * 1024,
                original_url=None,
                resample_cost=0,
                resample_size=0,
                resample_url=None,
            )

    client = NoResampleClient()
    with pytest.raises(ArchiveNotRetryableError):
        await Downloader(client, tmp_path).execute(
            DownloadTask(1, "t", "title", id=1, mode="archive", quality="resample")
        )
    assert client.requests == []
