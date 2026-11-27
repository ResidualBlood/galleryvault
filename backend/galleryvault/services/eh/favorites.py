from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ...logging import log_extra
from ..eh_parsers import (
    EhClientError,
    FavoriteData,
    FavoriteItems,
    _favorites_next_url,
    _favorites_page_favcats,
    _is_auth_failure_page,
    _is_favorites_auth_failure_page,
    _is_ip_banned_page,
    _parse_favorite_categories,
    _parse_favorite_counts,
    _search_item_window,
    _text,
    parse_favorite_note,
    parse_gallery_url,
)
from .session import EXHENTAI_API_CHUNK_SIZE

logger = logging.getLogger("galleryvault.services.eh_client")

def _validate_favorites_write_response(
    response: httpx.Response, *, target_favcat: int | None = None
) -> None:
    """Reject HTTP-200 responses that are not a confirmed favorites page.

    ExHentai answers a favorites POST with HTTP 200 even when the session is
    dead, the IP is banned, or the client is being rate limited; following
    redirects means ``raise_for_status`` never fires.  Callers must not treat
    such a body as "favorites changed", so require the favorites page identity
    (folder markers) and, for moves, that the target folder is present.
    """
    if response.status_code in (401, 403) or "login" in str(response.url).lower():
        raise EhClientError("ExHentai authentication is required or expired")
    body = response.text or ""
    if _is_favorites_auth_failure_page(body) or _is_ip_banned_page(body):
        raise EhClientError("ExHentai authentication is required or expired")
    if not body.strip():
        raise EhClientError("ExHentai favorites response was empty")
    favcats = _favorites_page_favcats(body)
    if not favcats:
        raise EhClientError("ExHentai favorites response was not the favorites page")
    if target_favcat is not None and int(target_favcat) not in favcats:
        raise EhClientError(
            f"ExHentai favorites move to folder {int(target_favcat)} was not confirmed"
        )

async def fetch_favorites(
    client,
    favcat: int,
    progress: Callable[[int], object] | None = None,
    *,
    max_pages: int | None = None,
) -> FavoriteItems:
    """Fetch every gallery in a favorite folder, following ExHentai paging.

    ExHentai favorites are paginated with a ``next`` cursor embedded in the
    page (``var nexturl="...?favcat=N&next=gid-timestamp"``) rather than a
    ``page`` number; walking only the first page silently drops the tail of
    a large folder.  ``progress`` (if given) is called with the number of
    galleries collected so far after every page.

    ``max_pages`` bounds the walk (``1`` is a single first-page probe used
    by the scheduled skip heuristic).  The header count is still parsed, so
    the returned object reports ``truncated`` honestly even for a probe.

    The returned :class:`FavoriteItems` records whether an empty result is
    confirmed by the folder header (``confirmed_empty``) and whether paging
    stopped short of the header count (``truncated``), so callers can avoid
    deleting local favorites on a partial or unparseable page.
    """
    result = FavoriteItems()
    seen: set[int] = set()
    header_counts: dict[int, int] | None = None
    url = "/favorites.php"
    params: dict[str, object] = {"favcat": int(favcat)}
    pages = 0
    while True:
        response = await client._get(url, params=params)
        # Identity check: a dead session or an anti-abuse redirect can land
        # on a generic page that still carries ``/g/`` links. Parsing it
        # would import homepage/search gids as favorites (and let the
        # pruner delete real rows), so require the favorites route, and
        # never treat a login/logout body as "empty favorites".
        final_path = urlparse(str(response.url)).path.rstrip("/")
        if final_path != "/favorites.php":
            raise EhClientError(
                f"ExHentai favorites request left the favorites page ({final_path or '/'})"
            )
        if _is_favorites_auth_failure_page(response.text):
            raise EhClientError("ExHentai authentication is required or expired")
        if header_counts is None:
            header_counts = _parse_favorite_counts(response.text)
        # The cover thumbnail lives in a SEPARATE link (the glthumb cell)
        # from the title link the loop below matches, so map gid -> thumb
        # from the whole page once and look it up per item.
        thumbs: dict[int, str] = {}
        for tm in re.finditer(
            r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>'
            r'\s*<img[^>]+src=["\']([^"\']+)["\']',
            response.text,
            re.IGNORECASE | re.DOTALL,
        ):
            try:
                tgid, _ = parse_gallery_url(tm.group(1), client.settings.exhentai_base_url)
            except ValueError:
                continue
            thumbs[tgid] = html.unescape(tm.group(2))
        items: list[FavoriteData] = []
        for href, label in re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:/g/|/gallery/)[^"\']*)["\'][^>]*>(?![^<]*<img)(.*?)</a>',
            response.text,
            re.IGNORECASE | re.DOTALL,
        ):
            try:
                gid, token = parse_gallery_url(href, client.settings.exhentai_base_url)
            except ValueError:
                continue
            if gid in seen:
                continue
            seen.add(gid)
            # ExHentai nests the whole tag table inside the title <a>, so
            # only the <div class="glink"> holds the actual title.
            glink = re.search(
                r'<div[^>]*class=["\']glink["\'][^>]*>(.*?)</div>',
                label,
                re.IGNORECASE | re.DOTALL,
            )
            title = _text(glink.group(1)) if glink else _text(label)
            snippet = _search_item_window(response.text, gid, token)
            items.append(
                FavoriteData(
                    gid,
                    token,
                    title,
                    urljoin(str(response.url), href),
                    thumbs.get(gid),
                    parse_favorite_note(snippet, gid),
                )
            )
        if not items:
            break
        result.extend(items)
        if progress is not None:
            progress(len(result))
        pages += 1
        if max_pages is not None and pages >= max_pages:
            break
        next_url = html.unescape(_favorites_next_url(response.text))
        if not next_url:
            break
        parsed = urlparse(next_url)
        url = parsed.path or "/favorites.php"
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    # Only the header count can confirm an empty folder or a short listing;
    # without it the result is "unknown" and callers must not prune on it.
    cloud_count = header_counts.get(int(favcat)) if header_counts else None
    result.cloud_count = cloud_count
    result.confirmed_empty = not result and cloud_count == 0
    result.truncated = cloud_count is not None and len(result) < cloud_count
    return result

async def fetch_favorite_categories(client) -> dict[int, str]:
    response = await client._get("/favorites.php")
    return _parse_favorite_categories(response.text)

async def fetch_favorite_counts(client) -> dict[int, int] | None:
    """Current per-folder gallery counts from one favorites.php request.

    Returns ``None`` when the page header could not be parsed (login wall,
    redirect, or markup drift). A parsed mapping is authoritative and may
    legitimately contain zeros (``{0: 0}`` = the folder is empty).
    """
    response = await client._get("/favorites.php")
    final_path = urlparse(str(response.url)).path.rstrip("/")
    if final_path != "/favorites.php":
        raise EhClientError(
            f"ExHentai favorites counts request left the favorites page "
            f"({final_path or '/'})"
        )
    if _is_favorites_auth_failure_page(response.text):
        raise EhClientError("ExHentai authentication is required or expired")
    return _parse_favorite_counts(response.text)

async def remove_favorites(client, gids: list[int]) -> list[int]:
    """Remove galleries from ExHentai favorites (across all folders).

    Mirrors Ehviewer_CN_SXJ: POST /favorites.php with ``ddact=delete`` and
    one ``modifygids[]`` entry per gid.  ExHentai caps each request at 25
    gids, so larger lists are chunked; a failed chunk is retried once per
    gid so one bad gallery cannot block the rest.  Returns the list of gids
    that could not be removed (empty on full success).
    """
    if not gids:
        return []
    failed: list[int] = []

    async def _post(gids_batch: list[int]) -> None:
        form = {
            "ddact": "delete",
            "apply": "Apply",
            "modifygids[]": [str(int(g)) for g in gids_batch],
        }
        response = await client._request(
            "POST",
            "/favorites.php",
            data=form,
            headers={
                "Referer": urljoin(str(client.client.base_url), "/favorites.php"),
                "Origin": client.settings.exhentai_base_url.rstrip("/"),
            },
        )
        client._raise_for_status(response)
        _validate_favorites_write_response(response)

    for chunk in (
        gids[i : i + EXHENTAI_API_CHUNK_SIZE]
        for i in range(0, len(gids), EXHENTAI_API_CHUNK_SIZE)
    ):
        try:
            await _post(chunk)
        except EhClientError:
            # Auth expiry is not a per-gallery failure: propagate so the
            # caller can surface a dead session instead of swallowing it.
            raise
        except Exception as exc:  # noqa: BLE001 - retry each gid on its own
            logger.info(
                "batch favorites remove failed; retrying per gid",
                extra=log_extra(chunk_size=len(chunk), error=str(exc)),
            )
            for gid in chunk:
                try:
                    await _post([gid])
                except Exception as single_exc:  # noqa: BLE001 - surface per-gid failures
                    logger.warning(
                        "per-gid favorites remove failed on cloud",
                        extra=log_extra(gid=gid, error=str(single_exc)),
                    )
                    failed.append(gid)
    return failed

async def move_favorites(client, gids: list[int], target_favcat: int) -> list[int]:
    """Move galleries to an ExHentai favorite folder (target_favcat 0..9).

    Mirrors favorites.php batch action: POST /favorites.php with
    ``ddact=fav{target_favcat}``, ``apply=Apply``, and ``modifygids[]``.
    Chunked at 25 gids per request.  Returns the list of gids that could
    not be moved (empty on full success).
    """
    if not gids:
        return []
    if not (0 <= target_favcat <= 9):
        raise ValueError("target_favcat must be between 0 and 9")
    failed: list[int] = []

    async def _post(gids_batch: list[int]) -> None:
        form = {
            "ddact": f"fav{int(target_favcat)}",
            "apply": "Apply",
            "modifygids[]": [str(int(g)) for g in gids_batch],
        }
        response = await client._request(
            "POST",
            "/favorites.php",
            data=form,
            headers={
                "Referer": urljoin(str(client.client.base_url), "/favorites.php"),
                "Origin": client.settings.exhentai_base_url.rstrip("/"),
            },
        )
        client._raise_for_status(response)
        _validate_favorites_write_response(response, target_favcat=target_favcat)

    for chunk in (
        gids[i : i + EXHENTAI_API_CHUNK_SIZE]
        for i in range(0, len(gids), EXHENTAI_API_CHUNK_SIZE)
    ):
        try:
            await _post(chunk)
        except EhClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - retry each gid on its own
            logger.info(
                "batch favorites move failed; retrying per gid",
                extra=log_extra(
                    chunk_size=len(chunk), target_favcat=target_favcat, error=str(exc)
                ),
            )
            for gid in chunk:
                try:
                    await _post([gid])
                except Exception as single_exc:  # noqa: BLE001 - surface per-gid failures
                    logger.warning(
                        "per-gid favorites move failed on cloud",
                        extra=log_extra(
                            gid=gid, target_favcat=target_favcat, error=str(single_exc)
                        ),
                    )
                    failed.append(gid)
    return failed

async def add_favorite(
    client, gid: int, token: str, favcat: int, note: str = ""
) -> None:
    """Add a single gallery to an ExHentai favorite folder (favcat 0..9).

    Mirrors EhEngine.addFavorites: POST /gallerypopups.php?gid={gid}&t={token}&act=addfav
    with favcat={favcat}, favnote={note}, update=1, submit=Apply Changes.
    """
    if not (0 <= favcat <= 9):
        raise ValueError("favcat must be between 0 and 9")
    form = {
        "favcat": str(int(favcat)),
        "favnote": note or "",
        "update": "1",
        "submit": "Apply Changes",
    }
    url = f"/gallerypopups.php?gid={int(gid)}&t={token}&act=addfav"
    response = await client._request(
        "POST",
        url,
        data=form,
        headers={
            "Referer": urljoin(str(client.client.base_url), url),
            "Origin": client.settings.exhentai_base_url.rstrip("/"),
        },
    )
    if (
        response.status_code in (401, 403)
        or "login" in str(response.url).lower()
        or _is_auth_failure_page(response.text)
        or _is_ip_banned_page(response.text)
    ):
        raise EhClientError("ExHentai authentication is required or expired")
    client._raise_for_status(response)

async def add_favorites(
    client, items: list[tuple[int, str]], favcat: int, note: str = ""
) -> list[int]:
    """Add multiple galleries to an ExHentai favorite folder.

    ExHentai does not provide a batch add endpoint, so galleries are processed
    individually (bounded by the shared semaphore). Returns list of failed gids.
    """
    if not items:
        return []
    if not (0 <= favcat <= 9):
        raise ValueError("favcat must be between 0 and 9")
    failed: list[int] = []
    finished: set[int] = set()
    try:
        for i, (gid, token) in enumerate(items):
            try:
                await client.add_favorite(gid, token, favcat, note=note)
                finished.add(gid)
            except EhClientError as exc:
                logger.warning(
                    "add favorite failed on cloud",
                    extra=log_extra(gid=gid, favcat=favcat, error=str(exc)),
                )
                failed.append(gid)
                finished.add(gid)
                msg = str(exc).lower()
                if "authentication" in msg or "expired" in msg:
                    failed.extend(g for g, _ in items[i + 1 :])
                    break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "add favorite failed on cloud",
                    extra=log_extra(gid=gid, favcat=favcat, error=str(exc)),
                )
                failed.append(gid)
                finished.add(gid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "add favorites aborted",
            extra=log_extra(favcat=favcat, error=str(exc)),
        )
        failed.extend(
            items[idx][0]
            for idx in range(len(items))
            if items[idx][0] not in finished
        )
    return failed
