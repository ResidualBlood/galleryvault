"""Tests for Downloader resume and existing page resolution across qualities."""

from pathlib import Path

import pytest

from galleryvault.services.downloader import (
    Downloader,
    DownloadTask,
    _existing_page_file,
)
from galleryvault.services.eh_client import GalleryData, GalleryPageData

VALID_JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20
VALID_WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20


def test_existing_page_file_respects_original_quality(tmp_path: Path) -> None:
    # 1. Directory with only valid webp
    (tmp_path / "00000001.webp").write_bytes(VALID_WEBP_BYTES)

    # original quality should ignore webp and return None
    assert _existing_page_file(tmp_path, 0, quality="original") is None
    assert _existing_page_file(tmp_path, 0, quality="ORIGINAL") is None

    # resample or default quality should accept webp
    assert _existing_page_file(tmp_path, 0, quality="resample") == tmp_path / "00000001.webp"
    assert _existing_page_file(tmp_path, 0) == tmp_path / "00000001.webp"

    # 2. Add valid jpg
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
        self, gid: int, page: GalleryPageData, showkey=None
    ) -> GalleryPageData:
        return GalleryPageData(
            page.index, page.url, page.token, f"https://img.test/{page.token}.jpg"
        )

    async def download_image(self, url: str) -> bytes:
        self.image_calls.append(url)
        return VALID_JPG_BYTES


@pytest.mark.asyncio
async def test_downloader_original_redownloads_when_only_webp_exists(
    tmp_path: Path,
) -> None:
    """Target directory has only 00000001.webp; original quality must redownload."""
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
async def test_downloader_original_skips_when_valid_jpg_exists(
    tmp_path: Path,
) -> None:
    """Target directory already has valid 00000001.jpg; original quality skips."""
    target_dir = tmp_path / "1-test_gallery"
    target_dir.mkdir()
    (target_dir / "00000001.jpg").write_bytes(VALID_JPG_BYTES)

    client = _CountingDownloaderClient()
    downloader = Downloader(client, tmp_path)
    task = DownloadTask(1, "tok", "test_gallery", quality="original")

    result = await downloader.execute(task)
    assert len(client.image_calls) == 0
    assert (result.path / "00000001.jpg").exists()
