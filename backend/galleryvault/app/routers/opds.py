"""OPDS catalog of recently ingested galleries (cookie auth required)."""

from __future__ import annotations

import html
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError

from ...db.repository import GalleryRepository
from ..dependencies import db_error, display_title, get_session

router = APIRouter()

_OPDS_LIMIT = 50


def _atom_date(value: datetime | None) -> str:
    if value is None:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/api/opds")
async def opds_catalog(request: Request) -> Response:
    try:
        async for session in get_session():
            _total, rows = await GalleryRepository(session).list_page(1, _OPDS_LIMIT)
            break
    except SQLAlchemyError as exc:
        raise db_error(exc) from exc
    base = str(request.base_url).rstrip("/")
    updated = _atom_date(datetime.now(UTC))
    entries: list[str] = []
    for row in rows:
        title = html.escape(display_title(row) or row.title or str(row.id))
        href = html.escape(f"{base}/api/galleries/{row.id}/export.cbz")
        updated_at = _atom_date(getattr(row, "created_at", None))
        entries.append(
            "\n".join(
                [
                    "  <entry>",
                    f"    <title>{title}</title>",
                    f"    <id>urn:galleryvault:gallery:{row.id}</id>",
                    f"    <updated>{updated_at}</updated>",
                    (
                        f'    <link rel="http://opds-spec.org/acquisition" '
                        f'href="{href}" type="application/vnd.comicbook+zip"/>'
                    ),
                    "  </entry>",
                ]
            )
        )
    body = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                '<feed xmlns="http://www.w3.org/2005/Atom" '
                'xmlns:opds="http://opds-spec.org/2010/catalog">'
            ),
            "  <id>urn:galleryvault:opds</id>",
            "  <title>GalleryVault</title>",
            f"  <updated>{updated}</updated>",
            (
                f'  <link rel="self" href="{html.escape(str(request.url))}" '
                'type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>'
            ),
            *entries,
            "</feed>",
            "",
        ]
    )
    return Response(content=body, media_type="application/atom+xml; charset=utf-8")
