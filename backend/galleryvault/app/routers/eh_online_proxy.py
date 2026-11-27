"""Optional server-side image proxy for the online reader.

Direct H@H fetching is the primary path; this endpoint is the per-device manual
fallback used when the browser cannot reach the image hosts.  It reuses the
resolve service (one ``showpage`` per page, shared ``online_reader_concurrency``
limit) and ``download_image_with_metadata`` (host allow-list, 509 detection and
the existing image/page semaphore budget), then serves the bytes from a small
on-disk cache with an ETag and ``Cache-Control: private``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from ...services.online_image_cache import (
    cache_etag,
    fetch_online_image,
    is_not_modified,
)
from ...services.online_resolve import OnlineResolveError
from ..dependencies import (
    get_current_settings,
    get_eh_client_manager,
    image_content_type,
)
from .eh_online import _validate_gid, _validate_token

router = APIRouter()

_CACHE_CONTROL = "private, max-age=86400"


def _read_head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(16)


@router.get("/api/eh/galleries/{gid}/{token}/pages/{n}/image")
async def eh_online_page_image(
    gid: int,
    token: str,
    n: int,
    request: Request,
    client_mgr: Any = Depends(get_eh_client_manager),  # noqa: B008
) -> Response:
    """Serve one reader page through the server, with a private disk cache."""
    gid = _validate_gid(gid)
    token = _validate_token(token)
    if n <= 0:
        raise HTTPException(status_code=404, detail={"code": "page_out_of_range"})

    settings = get_current_settings()
    try:
        path = await fetch_online_image(client_mgr, gid, token, n, settings)
    except OnlineResolveError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code}
        ) from exc

    if not path.is_file():
        # The cache tree can be pruned by a concurrent request between the
        # fetch and the stat; treat that as a transient upstream failure.
        raise HTTPException(status_code=502, detail={"code": "upstream"})

    etag = cache_etag(path)
    headers: dict[str, str] = {"Cache-Control": _CACHE_CONTROL}
    if etag:
        headers["ETag"] = etag
        if is_not_modified(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)

    head = await run_in_threadpool(_read_head, path)
    return FileResponse(path, media_type=image_content_type(head), headers=headers)
