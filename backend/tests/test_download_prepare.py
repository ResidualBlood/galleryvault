"""Title resolve, replacement-chain parse, and follow-mode helpers."""

from __future__ import annotations

from galleryvault.services.downloader import (
    DownloadTask,
    follow_download_updates,
    raise_if_replaced,
)
from galleryvault.services.eh_client import (
    GalleryData,
    GalleryReplacedError,
    parse_newer_gallery,
)


def test_parse_newer_gallery_reads_replacement_link() -> None:
    body = (
        "<p>This gallery has been replaced with a newer version of the gallery.</p>"
        '<p><a href="https://exhentai.org/g/99/abcdef1234/">Click here</a></p>'
    )
    assert parse_newer_gallery(body, 1) == (99, "abcdef1234")


def test_parse_newer_gallery_ignores_current_gid_and_unrelated_pages() -> None:
    assert parse_newer_gallery('<a href="/g/1/aaaaaa/">self</a>', 1) is None
    body = (
        "This gallery has been replaced with a newer version"
        '<a href="/g/1/oldtoken/">old</a>'
        '<a href="/g/22/newtoken/">new</a>'
    )
    assert parse_newer_gallery(body, 1) == (22, "newtoken")


def test_parse_newer_gallery_ignores_parent_link_before_hint() -> None:
    body = (
        '<a href="/g/10/parenttok/">Parent</a>'
        "<p>This gallery has been replaced with a newer version of the gallery.</p>"
        '<a href="/g/99/newertok/">Click here</a>'
    )
    assert parse_newer_gallery(body, 50) == (99, "newertok")


def test_follow_download_updates_skips_gallery_original_mode() -> None:
    assert follow_download_updates(None) is True
    assert follow_download_updates("archive") is True
    assert follow_download_updates("favorite") is True
    assert follow_download_updates("gallery") is False
    assert follow_download_updates("gallery_archive") is False


def test_raise_if_replaced_for_paste_not_gallery_mode() -> None:
    from galleryvault.services.eh_client import GalleryGoneError

    gallery = GalleryData(1, "old", "t", [], replaced_by=(2, "new"))
    try:
        raise_if_replaced(DownloadTask(1, "old", "t", mode="archive"), gallery)
        raise AssertionError("expected GalleryReplacedError")
    except GalleryReplacedError as exc:
        assert exc.new_gid == 2
        assert exc.new_token == "new"
    try:
        raise_if_replaced(DownloadTask(1, "old", "t", mode="gallery"), gallery)
        raise AssertionError("expected GalleryGoneError")
    except GalleryGoneError:
        pass
    try:
        raise_if_replaced(DownloadTask(1, "old", "t", mode="gallery_archive"), gallery)
        raise AssertionError("expected GalleryGoneError")
    except GalleryGoneError:
        pass
