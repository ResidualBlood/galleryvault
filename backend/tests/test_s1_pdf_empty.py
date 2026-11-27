"""S1: page-less PDFs are rejected and counted as scan errors, not ingested."""

from pathlib import Path

import pytest

from galleryvault.services.library import LibraryService


def test_pageless_pdf_counted_as_error_not_ingested(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    root = tmp_path / "library"
    root.mkdir()
    path = root / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as fh:
        writer.write(fh)

    service = LibraryService([root])
    galleries = [gallery for batch in service.scan_batches() for gallery in batch]

    assert galleries == []
    assert service.last_counters.errors == 1
    assert service.last_counters.success == 0
