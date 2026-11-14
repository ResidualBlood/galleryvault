from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ...logging import log_extra
from ..eh_parsers import (
    _NEXT_CURSOR_RE,
    _TOPLIST_CURSOR_RE,
    EhClientError,
    EhSearchResult,
    _toplist_next_cursor,
    classify_search_body,
    normalize_jump,
    normalize_seek,
    parse_search_page,
    parse_search_prev_cursor,
)

logger = logging.getLogger("galleryvault.services.eh_client")

def _search_response_urls(response: httpx.Response) -> list[str]:
    urls = [str(response.url)]
    urls.extend(str(hist.url) for hist in (response.history or []))
    loc = response.headers.get("location")
    if loc:
        urls.append(str(loc))
    return urls

def classify_search_response(response: httpx.Response) -> str:
    """Classify HTTP-level search failures. ``ok`` means continue to the body."""
    status = response.status_code
    if status in (429, 509):
        return "rate_limited"
    if any("remoteapi.php" in url.lower() for url in _search_response_urls(response)):
        return "challenge"
    if status in (401, 403):
        return "not_logged_in"
    if "login" in str(response.url).lower():
        return "not_logged_in"
    return "ok"

async def search_galleries(
    client,
    *,
    q: str = "",
    f_cats: int | None = None,
    min_rating: float | None = None,
    next_cursor: str | None = None,
    prev_cursor: str | None = None,
    list_type: str = "search",
    tl: int | None = None,
    jump: str | None = None,
    seek: str | None = None,
) -> EhSearchResult:
    """Fetch one ExHentai listing (cursor, not ``page=N``).

    ``list_type``: ``search`` (``/``), ``popular`` (``/popular``),
    ``watched`` (``/watched``), ``toplist`` (``/toplist.php?tl=``).
    Toplist ``tl`` values match the site: 11 yesterday / 12 month /
    13 year / 15 all-time.

    ``prev_cursor`` walks back via the list ``prev=`` cursor and is
    mutually exclusive with ``next_cursor``.  ``jump`` (``1d`` … ``2y``)
    and ``seek`` (``YYYY-MM-DD``) are E-Hentai's date-jump parameters and
    extend an existing cursor, so one of ``next_cursor`` / ``prev_cursor``
    is required (same contract as EhViewer's date-jump dialog).
    """
    kind = (list_type or "search").strip().lower()
    if kind not in {"search", "popular", "watched", "toplist"}:
        raise ValueError("invalid list")
    if next_cursor and prev_cursor:
        raise ValueError("next and prev are mutually exclusive")
    jump_value = normalize_jump(jump)
    seek_value = normalize_seek(seek)
    if jump_value and seek_value:
        raise ValueError("jump and seek are mutually exclusive")
    if jump_value or seek_value:
        if kind == "toplist":
            raise ValueError("toplist uses page cursors, not date jump")
        if not (next_cursor or prev_cursor):
            raise ValueError("date jump requires a cursor")
    params: dict[str, object] = {}
    path = "/"
    if kind == "popular":
        path = "/popular"
    elif kind == "watched":
        path = "/watched"
    elif kind == "toplist":
        path = "https://e-hentai.org/toplist.php"
        tl_value = 15 if tl is None else int(tl)
        if tl_value not in {11, 12, 13, 15}:
            raise ValueError("invalid toplist tl")
        params["tl"] = tl_value
    if kind in {"search", "watched"} and q and str(q).strip():
        params["f_search"] = str(q).strip()
    if kind == "search" and f_cats is not None:
        params["f_cats"] = int(f_cats)
    cur_p = 0
    if next_cursor:
        if kind == "toplist":
            if not _TOPLIST_CURSOR_RE.fullmatch(str(next_cursor)) or not (
                0 <= int(next_cursor) < 200
            ):
                raise ValueError("invalid next cursor")
            cur_p = int(next_cursor)
            if cur_p > 0:
                params["p"] = cur_p
        else:
            if not _NEXT_CURSOR_RE.fullmatch(str(next_cursor)):
                raise ValueError("invalid next cursor")
            params["next"] = str(next_cursor)
    elif prev_cursor:
        if kind == "toplist":
            if not _TOPLIST_CURSOR_RE.fullmatch(str(prev_cursor)) or not (
                0 <= int(prev_cursor) < 200
            ):
                raise ValueError("invalid prev cursor")
            cur_p = int(prev_cursor)
            if cur_p > 0:
                params["p"] = cur_p
        else:
            if not _NEXT_CURSOR_RE.fullmatch(str(prev_cursor)):
                raise ValueError("invalid prev cursor")
            params["prev"] = str(prev_cursor)
    if jump_value:
        params["jump"] = jump_value
    if seek_value:
        params["seek"] = seek_value
    if kind in {"search", "watched"} and min_rating is not None:
        srdd = max(2, min(5, int(min_rating)))
        params["advsearch"] = 1
        params["f_sr"] = "on"
        params["f_srdd"] = srdd
    req_kwargs: dict[str, Any] = {"params": params}
    if kind == "toplist":
        raw_cookies = getattr(client.settings, "exhentai_cookies", None)
        cookies: dict[str, str] = {}
        if isinstance(raw_cookies, dict):
            cookies = {str(k): str(v) for k, v in raw_cookies.items()}
        elif isinstance(raw_cookies, str) and raw_cookies.strip():
            try:
                import json as _json

                parsed = _json.loads(raw_cookies)
                if isinstance(parsed, dict):
                    cookies = {str(k): str(v) for k, v in parsed.items()}
            except Exception:  # noqa: BLE001, S110
                pass
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            req_kwargs["headers"] = {"Cookie": cookie_str}
    try:
        response = await client._request("GET", path, **req_kwargs)
    except httpx.RequestError as exc:
        logger.warning("ExHentai search failed", extra=log_extra(error=type(exc).__name__))
        raise EhClientError("ExHentai request failed") from exc
    state = classify_search_response(response)
    if state != "ok":
        return EhSearchResult(items=[], next_cursor=None, state=state)
    if response.status_code >= 400:
        raise EhClientError(f"ExHentai returned HTTP {response.status_code}")
    try:
        await response.aread()
    except httpx.RequestError as exc:
        raise EhClientError("ExHentai request failed") from exc
    body = response.text
    state = classify_search_body(body)
    if state != "ok":
        return EhSearchResult(items=[], next_cursor=None, state=state)
    items, nxt = parse_search_page(
        body, "https://e-hentai.org" if kind == "toplist" else str(client.settings.exhentai_base_url)
    )
    if kind == "toplist":
        nxt = _toplist_next_cursor(body, cur_p)
        prv = str(cur_p - 1) if cur_p > 0 else None
    else:
        prv = parse_search_prev_cursor(body)
    if items:
        return EhSearchResult(
            items=items, next_cursor=nxt, state="ok", prev_cursor=prv
        )
    if next_cursor or prev_cursor:
        return EhSearchResult(
            items=[], next_cursor=None, state="ok", prev_cursor=prv
        )
    if re.search(r"No hits found", body, re.IGNORECASE):
        return EhSearchResult(items=[], next_cursor=None, state="empty")
    if 'name="f_search"' in body or "itg" in body.lower():
        return EhSearchResult(items=[], next_cursor=None, state="empty")
    return EhSearchResult(items=[], next_cursor=None, state="challenge")
