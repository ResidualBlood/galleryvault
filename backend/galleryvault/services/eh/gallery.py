from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from ...logging import log_extra
from ..eh_parsers import (
    IMAGE_RE,
    PAGE_RE,
    SHOWKEY_RE,
    SHOWPAGE_IMAGE_RE,
    SHOWPAGE_ORIGIN_PROMPT_RE,
    SHOWPAGE_ORIGIN_RE,
    SHOWPAGE_SKIP_KEY_RE,
    VIEWER_HREF_RE,
    EhAuthRequiredError,
    EhBannedError,
    EhChallengeError,
    EhClientError,
    EhParseError,
    EhQuotaExceededError,
    GalleryData,
    GalleryGoneError,
    GalleryPageData,
    OnlineGalleryDetail,
    PreviewPage,
    ShowkeyState,
    _is_auth_failure_page,
    _is_exhentai_org_host,
    _is_ip_banned_page,
    _parse_category,
    _parse_file_size,
    _parse_gallery_titles,
    _parse_tags,
    parse_gallery_preview,
    parse_gallery_url,
    parse_login_state,
    parse_newer_gallery,
    parse_online_gallery,
)
from .session import EXHENTAI_API_CHUNK_SIZE, _quota_exceeded_error

logger = logging.getLogger("galleryvault.services.eh_client")

def _page_token_from_href(absolute: str) -> str | None:
    """Extract the 10-hex pToken from a viewer URL (mirrors Ehviewer_CN_SXJ).

    Tries the current ``/s/<pToken>/<gid>-<page>`` format, then the legacy
    3-segment format, then the query ``p`` parameter.
    """
    viewer = VIEWER_HREF_RE.search(absolute)
    if viewer:
        return viewer.group("ptoken")
    legacy = PAGE_RE.search(urlparse(absolute).path)
    if legacy:
        return legacy.group("page")
    return parse_qs(urlparse(absolute).query).get("p", [""])[0] or None

async def check_login(client) -> tuple[str, str]:
    """Probe ExHentai and return ``(state, detail)``.

    ``state`` is one of ``ok`` / ``not_logged_in`` / ``no_exhentai_access`` /
    ``ip_banned`` / ``failed``; ``detail`` carries the HTTP status or exception type for the
    failure message. Probes ``/uconfig.php`` (a member-only settings page):
    every session state answers HTTP 200, but the body distinguishes them —
    a full page for a valid session, ``expired login session`` for a dead
    one, and an empty/blank body when no cookies or no access are present.
    Retries once on transport errors or empty/blank 200 responses.
    """
    last_error: Exception | None = None
    last_response: httpx.Response | None = None
    for _ in range(2):
        try:
            response = await client._request("GET", "/uconfig.php")
        except httpx.RequestError as exc:
            last_error = exc
            last_response = None
            continue
        last_response = response
        if response.status_code in (401, 403) or "login" in str(response.url).lower():
            return "not_logged_in", f"HTTP {response.status_code}"
        body = response.text
        if _is_ip_banned_page(body):
            return "ip_banned", f"HTTP {response.status_code}"
        if _is_auth_failure_page(body):
            return "no_exhentai_access", f"HTTP {response.status_code}"
        if not body or not body.strip():
            continue
        host = (
            urlparse(str(response.url)).hostname
            or urlparse(client.settings.exhentai_base_url).hostname
        )
        return (
            parse_login_state(body, host=host),
            f"HTTP {response.status_code}",
        )
    if last_response is not None:
        host = (
            urlparse(str(last_response.url)).hostname
            or urlparse(client.settings.exhentai_base_url).hostname
        )
        state = "no_exhentai_access" if _is_exhentai_org_host(host) else "failed"
        return state, f"HTTP {last_response.status_code}"
    return "failed", type(last_error).__name__

async def probe_challenge(client, sample_path: str = "/") -> bool:
    """Probe ExHentai to check if the 302 anti-abuse challenge has cleared."""
    try:
        response = await client._get(sample_path)
        url_str = str(response.url)
        if "remoteapi.php" in url_str or "poni=no" in url_str:
            return False
        return not (sample_path.startswith("/g/") and not str(response.url.path).startswith("/g/"))
    except Exception:  # noqa: BLE001
        return False

async def fetch_gallery_metadata(client, gid: int, token: str) -> GalleryData:
    """Fetch only gallery metadata; tag sync must not enumerate or download pages."""
    response = await client._get(f"/g/{int(gid)}/{token}/")
    # Mirror fetch_gallery's anti-abuse challenge guard: ExHentai sometimes
    # 302s through remoteapi.php and lands on "/" with no content. The
    # cookie is still valid — treat as transient, not "gone".
    if not str(response.url.path).startswith("/g/"):
        raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
    body = response.text
    if _is_auth_failure_page(body) or _is_ip_banned_page(body):
        raise EhClientError("ExHentai authentication is required or expired")
    if not body or not body.strip():
        raise EhClientError("ExHentai returned empty gallery page (temporary anti-abuse)")
    title, title_jpn = _parse_gallery_titles(body)
    tags = _parse_tags(body)
    newer = parse_newer_gallery(body, int(gid))
    if not title and newer is None:
        # ExHentai answers non-existent / deleted galleries with a tiny
        # 200 page that has no title (or a real 404). But an empty/challenged
        # page also has no title — the guards above already filtered those, so
        # this remaining case is a genuine gone gallery.
        raise GalleryGoneError("gallery does not exist on ExHentai")
    return GalleryData(
        int(gid), token, title, [], tags, _parse_category(body), title_jpn,
        _parse_file_size(body), newer,
    )

async def _fetch_gallery_html(
    client, gid: int, token: str, *, page: int | None = None
) -> httpx.Response:
    """Fetch a gallery page (optionally ``?p=N``) and classify its state.

    Unlike :meth:`_get`, this raises the *distinguishable* auth/banned
    exceptions so online endpoints can pass ``state`` through verbatim.
    """
    base = f"/g/{int(gid)}/{token}/"
    kwargs: dict[str, Any] = {}
    if page is not None:
        kwargs["params"] = {"p": int(page)}
    try:
        response = await client._request("GET", base, **kwargs)
        await response.aread()
    except httpx.RequestError as exc:
        logger.warning(
            "ExHentai gallery fetch failed", extra=log_extra(error=type(exc).__name__)
        )
        raise EhClientError("ExHentai request failed") from exc
    if response.status_code in (401, 403) or "login" in str(response.url).lower():
        raise EhAuthRequiredError("ExHentai authentication is required or expired")
    if response.status_code in (429, 509):
        raise _quota_exceeded_error(response)
    body = response.text
    if _is_ip_banned_page(body):
        raise EhBannedError("ExHentai IP address is banned")
    if _is_auth_failure_page(body):
        raise EhAuthRequiredError("ExHentai authentication is required or expired")
    if response.status_code >= 400:
        client._raise_for_status(response, gallery_404=True)
    # ExHentai's remoteapi.php anti-bot challenge 302s to the site root.
    if not str(response.url.path).startswith("/g/"):
        raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
    if not body.strip():
        raise EhClientError("ExHentai returned empty gallery page (temporary anti-abuse)")
    return response

async def fetch_online_gallery(client, gid: int, token: str) -> OnlineGalleryDetail:
    """One online-detail payload: gallery HTML plus best-effort gdata.

    The HTML page is authoritative (and the only required request); gdata
    is a typed-value enrichment, so a failed gdata chunk must not turn a
    readable detail page into an error.
    """
    response = await client._fetch_gallery_html(int(gid), token)
    gdata: dict[str, Any] = {}
    try:
        fetched = await client.fetch_gmetadata([(int(gid), token)])
    except EhClientError as exc:
        logger.warning(
            "ExHentai gdata lookup failed for online detail",
            extra=log_extra(error=str(exc)),
        )
    else:
        gdata = fetched.get(int(gid)) or {}
    return parse_online_gallery(response.text, int(gid), token, gdata=gdata)

async def fetch_gallery_preview_page(
    client, gid: int, token: str, page: int = 0
) -> PreviewPage:
    """Fetch one ``?p=`` preview page (page indices + sprite thumbnails)."""
    response = await client._fetch_gallery_html(int(gid), token, page=page)
    return parse_gallery_preview(response.text, int(gid))

async def fetch_gallery(
    client,
    gid: int | str,
    token: str | None = None,
    max_pages: int | None = None,
    *,
    resolve_urls: bool = True,
) -> GalleryData:
    if token is None:
        gid, token = parse_gallery_url(str(gid), client.settings.exhentai_base_url)
    base = f"/g/{int(gid)}/{token}/"
    response = await client._get(base)
    # ExHentai's remoteapi.php anti-bot challenge: the /g/ URL 302s through
    # forums.e-hentai.org/remoteapi.php?ex=… and lands on the site root
    # (…/?poni=no). The session cookie is fine — the IP is being
    # rate-challenged temporarily. Callers treat this as retryable.
    if not str(response.url.path).startswith("/g/"):
        raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
    body = response.text
    title, title_jpn = _parse_gallery_titles(body)
    newer = parse_newer_gallery(body, int(gid))
    if newer is not None:
        return GalleryData(
            int(gid),
            token,
            title,
            [],
            _parse_tags(body),
            _parse_category(body),
            title_jpn,
            _parse_file_size(body),
            newer,
        )
    # ExHentai lists roughly 20 page links per gallery page and paginates
    # long galleries with ?p=N.  Enumerate every gallery sub-page so whole
    # galleries are downloaded, not just the first screenful.
    page_hrefs: list[str] = []
    seen: set[str] = set()
    gid_pattern = re.compile(rf"/s/[0-9a-fA-F]+/{int(gid)}-\d+", re.IGNORECASE)

    def _collect_hrefs(page_body: str, limit: int | None = None) -> int:
        """Collect viewer hrefs from one gallery page; returns count added."""
        collected = 0
        for href in re.findall(
            r'<a[^>]+href=["\']([^"\']+)["\']', page_body, re.IGNORECASE
        ):
            if gid_pattern.search(href) and href not in seen:
                seen.add(href)
                page_hrefs.append(href)
                collected += 1
        if limit is not None and limit > 0 and len(page_hrefs) >= limit:
            del page_hrefs[limit:]
            seen.clear()
            seen.update(page_hrefs)
        return collected

    # Size the enumeration with gdata's filecount so the gallery sub-pages
    # can be fetched concurrently instead of serially (a 255-page gallery
    # previously walked 13 pages one at a time).
    estimate = 0
    try:
        gdata = await client.fetch_gmetadata([(int(gid), token)])
        info = gdata.get(int(gid)) or {}
        estimate = int(info.get("file_count") or 0)
    except Exception:  # noqa: BLE001 - fall back to sequential enumeration
        estimate = 0
    gallery_pages = max(1, (estimate + 19) // 20) if estimate > 0 else 0
    _collect_hrefs(body, max_pages)
    start = 1
    truncated_by_limit = (
        max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages
    )
    if gallery_pages > 1 and not truncated_by_limit:
        offsets = list(range(1, min(gallery_pages, 512)))

        async def _fetch_page(offset: int) -> tuple[int, str]:
            page_response = await client._get(f"{base}?p={offset}")
            if not str(page_response.url.path).startswith("/g/"):
                raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
            return offset, page_response.text

        fetched: dict[int, str] = {}
        try:
            for offset, text in await asyncio.gather(
                *(_fetch_page(o) for o in offsets)
            ):
                fetched[offset] = text
        except EhChallengeError:
            raise
        except Exception:  # noqa: BLE001 - redo the range serially below
            fetched = {}
        if fetched:
            for offset in sorted(fetched):
                if _collect_hrefs(fetched[offset], max_pages) == 0:
                    break
                if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                    break
            # The gdata filecount may be stale or undercount: keep walking
            # from the end of the concurrent batch until a page is empty.
            start = max(offsets) + 1
    if not truncated_by_limit:
        # Serial tail walk. Fix for stale gdata under-report: the old
        # ``gallery_pages + 2`` guard truncated long galleries when gdata
        # file_count was outdated (e.g. actual 255 pages but gdata said 20
        # => only 2 extra pages walked). Now walk until two consecutive
        # empty pages, which tolerates a single glitched page but still
        # terminates, and is unbounded when estimate==0. A hard 5000-offset
        # cap (~100k images) prevents an infinite loop if the server echoes
        # content.
        offset = start
        empty_streak = 0
        while True:
            if offset > 5000:
                break
            page_response = await client._get(f"{base}?p={offset}")
            if not str(page_response.url.path).startswith("/g/"):
                raise EhChallengeError("ExHentai is challenging this client (temporary anti-abuse)")
            collected = _collect_hrefs(page_response.text, max_pages)
            if collected == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                # One empty after we have passed estimate+2 could be real tail,
                # but require two empties to be safe against a transient gap.
                offset += 1
                continue
            empty_streak = 0
            if max_pages is not None and max_pages > 0 and len(page_hrefs) >= max_pages:
                break
            offset += 1
    if not page_hrefs:
        raise EhParseError("gallery HTML did not contain a title and page links")
    if resolve_urls:
        pages = await client._resolve_gallery_pages(int(gid), str(response.url), page_hrefs)
    else:
        # Lazy mode: return index + viewer URL + pToken only, leaving
        # image_url empty.  The downloader resolves each page's URL right
        # before fetching (see resolve_page) so a long download never
        # serves a keystamp that has already expired.
        pages = [
            GalleryPageData(
                index,
                urljoin(str(response.url), html.unescape(href)),
                _page_token_from_href(
                    urljoin(str(response.url), html.unescape(href))
                ),
            )
            for index, href in enumerate(page_hrefs)
        ]
    if not title:
        raise EhParseError("gallery HTML did not contain a title and page links")
    tags = _parse_tags(body)
    return GalleryData(
        int(gid), token, title, pages, tags, _parse_category(body), title_jpn
    )

async def _resolve_gallery_pages(
    client, gid: int, base_url: str, page_hrefs: list[str]
) -> list[GalleryPageData]:
    """Resolve every viewer href to its image URL (mirrors Ehviewer_CN_SXJ).

    The first page is resolved via full HTML so its ``showkey`` is available
    for the lightweight ``showpage`` API on the remaining pages.  All pages
    resolve concurrently (bounded by the shared ExHentai semaphore): serial
    resolution of a 255-page gallery took minutes.
    """
    showkey = ShowkeyState()

    async def _resolve_page_html(href: str) -> GalleryPageData:
        """Resolve one viewer page from its full HTML (also yields the showkey)."""
        absolute = urljoin(base_url, html.unescape(href))
        p_token = _page_token_from_href(absolute)
        page_response = await client._get(absolute)
        body = page_response.text
        image_match = None
        for image_tag in IMAGE_RE.finditer(body):
            tag = image_tag.group(0)
            if re.search(r'\bid=["\']img["\']', tag, re.IGNORECASE):
                image_match = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
                if image_match:
                    break
        if not image_match:
            raise EhClientError(f"viewer page has no image: {absolute}")
        image_url = urljoin(str(page_response.url), html.unescape(image_match.group(1)))
        origin_match = re.search(
            r'<a[^>]+href=["\']([^"\']+)fullimg([^"\']+)["\']', body, re.IGNORECASE
        )
        nl_match = re.search(r"nl\(\s*['\"](.*?)['\"]\s*\)", body)
        showkey_match = SHOWKEY_RE.search(body)
        if showkey_match:
            # Always refresh from the latest viewer page: a showkey expires
            # after a while, so HTML fallbacks must re-seed it or every
            # remaining page pays for a failing showpage call plus its HTML
            # fallback.
            showkey.value = showkey_match.group(1)
        origin_url = (
            urljoin(str(page_response.url), html.unescape(origin_match.group(1)))
            + "fullimg"
            + html.unescape(origin_match.group(2))
            if origin_match
            else None
        )
        return GalleryPageData(
            -1,
            absolute,
            p_token or "",
            image_url,
            origin_url,
            html.unescape(nl_match.group(1)) if nl_match else None,
        )

    async def _resolve_page_api(href: str) -> GalleryPageData:
        """Resolve one viewer page through the lightweight ``showpage`` API.

        Mirrors Ehviewer_CN_SXJ's ``getGalleryPageApi``: one POST to api.php
        returns JSON ``{i3, i6, i7}`` carrying the resample URL, the H@H
        skip key and the original (fullimg) URL — far smaller and stabler to
        parse than the whole viewer-page HTML.  Requires the pToken from the
        gallery-page preview links plus a ``showkey`` (from the first viewer
        page); falls back to HTML on any failure.
        """
        absolute = urljoin(base_url, html.unescape(href))
        viewer = VIEWER_HREF_RE.search(absolute)
        if not viewer:
            return await _resolve_page_html(href)
        p_token = viewer.group("ptoken")
        page = int(viewer.group("page"))
        if not showkey.value:
            return await _resolve_page_html(href)
        try:
            info = await client._showpage(gid, page, p_token, showkey.value, absolute)
        except EhClientError:
            # API hiccup (stale showkey, throttled, changed markup): fall back
            # to the full HTML path, which re-seeds showkey if needed.
            return await _resolve_page_html(href)
        return GalleryPageData(
            -1,
            absolute,
            p_token,
            info["image_url"],
            info["origin_url"],
            info["skip_hath_key"],
        )

    if page_hrefs:
        first = await _resolve_page_html(page_hrefs[0])
        pages = [first]
        if len(page_hrefs) > 1:
            pages.extend(
                await asyncio.gather(
                    *(_resolve_page_api(h) for h in page_hrefs[1:])
                )
            )
    return [
        GalleryPageData(
            index, r.url, r.token, r.image_url, r.origin_url, r.skip_hath_key
        )
        for index, r in enumerate(pages)
    ]

async def resolve_page(
    client,
    gid: int,
    page: GalleryPageData,
    showkey: ShowkeyState | None = None,
    *,
    skip_hath: bool = False,
) -> GalleryPageData:
    """Resolve one page's fresh image URLs right before downloading.

    Called by the downloader per page so the keystamp is never stale (a
    long gallery would otherwise serve URLs signed 20 minutes earlier,
    which H@H nodes reject with 403).  Prefers the lightweight showpage
    API when a showkey is known and falls back to full HTML otherwise.
    """
    if showkey is None:
        showkey = ShowkeyState()
    if skip_hath:
        if not page.skip_hath_key:
            page = await client._resolve_page_from_html(gid, page, showkey)
        if page.skip_hath_key:
            parsed = urlparse(page.url)
            query_pairs = [
                (k, v)
                for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                if k != "nl"
            ]
            query_pairs.append(("nl", page.skip_hath_key))
            target_url = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    urlencode(query_pairs),
                    parsed.fragment,
                )
            )
            target_page = replace(page, url=target_url)
            return await client._resolve_page_from_html(gid, target_page, showkey)
    absolute = page.url
    viewer = VIEWER_HREF_RE.search(absolute)
    p_token = viewer.group("ptoken") if viewer else (page.token or "")
    page_num = int(viewer.group("page")) if viewer else page.index + 1
    if showkey.value:
        try:
            info = await client._showpage(
                gid, page_num, p_token, showkey.value, absolute
            )
        except EhClientError:
            # Stale showkey / throttled API: fall back to HTML, which
            # re-seeds the showkey (same as fetch_gallery does).
            return await client._resolve_page_from_html(gid, page, showkey)
        return GalleryPageData(
            page.index,
            absolute,
            p_token,
            info["image_url"],
            info["origin_url"],
            info["skip_hath_key"],
        )
    return await client._resolve_page_from_html(gid, page, showkey)

async def _resolve_page_from_html(
    client, gid: int, page: GalleryPageData, showkey: ShowkeyState | None = None
) -> GalleryPageData:
    """Full-HTML resolution for a single page (mirrors ``_resolve_page_html``).

    Used by ``resolve_page`` when no showkey is available or the showpage
    API rejects.  Reuses the fresh viewer HTML so the image URL, origin URL
    and H@H skip key are all current.
    """
    absolute = page.url
    p_token = _page_token_from_href(absolute)
    page_response = await client._get(absolute)
    body = page_response.text
    image_match = None
    for image_tag in IMAGE_RE.finditer(body):
        tag = image_tag.group(0)
        if re.search(r'\bid=["\']img["\']', tag, re.IGNORECASE):
            image_match = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if image_match:
                break
    if not image_match:
        raise EhClientError(f"viewer page has no image: {absolute}")
    image_url = urljoin(str(page_response.url), html.unescape(image_match.group(1)))
    origin_match = re.search(
        r'<a[^>]+href=["\']([^"\']+)fullimg([^"\']+)["\']', body, re.IGNORECASE
    )
    nl_match = re.search(r"nl\(\s*['\"](.*?)['\"]\s*\)", body)
    showkey_match = SHOWKEY_RE.search(body)
    if showkey_match and showkey is not None:
        showkey.value = showkey_match.group(1)
    origin_url = (
        urljoin(str(page_response.url), html.unescape(origin_match.group(1)))
        + "fullimg"
        + html.unescape(origin_match.group(2))
        if origin_match
        else None
    )
    return GalleryPageData(
        page.index,
        absolute,
        p_token or "",
        image_url,
        origin_url,
        html.unescape(nl_match.group(1)) if nl_match else None,
    )

async def _showpage(
    client,
    gid: int,
    page: int,
    p_token: str,
    showkey: str,
    referer: str | None = None,
) -> dict[str, str]:
    """Resolve one page's image URLs via the ExHentai ``showpage`` API.

    ``page`` is 1-based.  Returns ``{image_url, origin_url, skip_hath_key}``
    exactly like parsing the viewer HTML would, but from a small JSON body.
    ``referer`` should be the gallery viewer URL this call originates from —
    ExHentai expects the browser-like Referer + Origin on its JSON API.
    """
    payload = {
        "method": "showpage",
        "gid": int(gid),
        "page": int(page),
        "imgkey": p_token,
        "showkey": showkey,
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if referer:
        headers["Referer"] = referer
    headers["Origin"] = client.settings.exhentai_base_url.rstrip("/")
    try:
        response = await client._request(
            "POST",
            "/api.php",
            json=payload,
            headers=headers,
        )
    except httpx.RequestError as exc:
        # Raw transport errors (e.g. ConnectTimeout) must surface as
        # EhClientError: callers treat it as retryable-with-backoff, whereas
        # a leaked httpx exception would retry immediately without the 30s
        # challenge backoff.
        logger.warning(
            "ExHentai showpage request failed",
            extra=log_extra(error=type(exc).__name__),
        )
        raise EhClientError("ExHentai request failed") from exc
    client._raise_for_status(response)
    try:
        body = response.json()
    except ValueError as exc:
        raise EhClientError("ExHentai showpage response was not JSON") from exc
    error = body.get("error")
    if error:
        raise EhClientError(f"ExHentai showpage error: {error}")
    i3 = body.get("i3") or ""
    i6 = body.get("i6") or ""
    i7 = body.get("i7")
    image_match = SHOWPAGE_IMAGE_RE.search(i3)
    if not image_match:
        raise EhClientError("ExHentai showpage returned no image URL")
    image_url = urljoin(str(response.url), html.unescape(image_match.group(1)))
    skip_match = SHOWPAGE_SKIP_KEY_RE.search(i6)
    skip_hath_key = html.unescape(skip_match.group(1)) if skip_match else None
    origin_url = None
    # Prefer the i7 ``fullimg`` link (the original-quality URL), matching the
    # HTML path and Ehviewer_CN_SXJ's preference for originImageUrl.  The i6
    # prompt URL is only a fallback when the origin link is missing.
    if i7 is not None:
        origin_match = SHOWPAGE_ORIGIN_RE.search(i7)
        if origin_match:
            origin_url = urljoin(
                str(response.url),
                html.unescape(origin_match.group(1))
                + "fullimg"
                + html.unescape(origin_match.group(2)),
            )
    if origin_url is None:
        prompt_match = SHOWPAGE_ORIGIN_PROMPT_RE.search(i6)
        if prompt_match:
            origin_url = urljoin(str(response.url), html.unescape(prompt_match.group(1)))
    return {
        "image_url": image_url,
        "origin_url": origin_url,
        "skip_hath_key": skip_hath_key,
    }

async def fetch_gmetadata(
    client, pairs: list[tuple[int, str]]
) -> dict[int, dict[str, Any]]:
    """Batch-fetch gallery metadata via the ExHentai ``gdata`` API.

    ExHentai caps each request at 25 galleries, so larger lists are chunked.
    Returns ``{gid: {thumb, title, title_jpn, category, file_count,
    file_size, tags}}`` for every gallery the API answered with.

    A chunk that fails is logged and skipped so the galleries already
    fetched are still returned; if no chunk succeeded the error is
    re-raised.  Quota/rate-limit errors abort immediately (retrying them
    would only deepen the limit).
    """
    result: dict[int, dict[str, Any]] = {}
    chunk_count = 0
    failed_chunks = 0
    last_error: EhClientError | None = None
    for start in range(0, len(pairs), EXHENTAI_API_CHUNK_SIZE):
        chunk_count += 1
        chunk = pairs[start : start + EXHENTAI_API_CHUNK_SIZE]
        payload = {
            "method": "gdata",
            "gidlist": [[int(gid), token] for gid, token in chunk],
            "namespace": 1,
        }
        try:
            response = await client._request(
                "POST",
                "/api.php",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Origin": client.settings.exhentai_base_url.rstrip("/"),
                },
            )
            client._raise_for_status(response)
            try:
                body = response.json()
            except ValueError as exc:
                raise EhClientError("ExHentai gdata response was not JSON") from exc
        except EhQuotaExceededError:
            raise
        except EhClientError as exc:
            # A failed chunk must not discard the chunks that already
            # succeeded: keep the partial result and only fail hard when
            # nothing at all came back (single-chunk callers keep the old
            # "raise on failure" contract).
            failed_chunks += 1
            last_error = exc
            logger.warning(
                "ExHentai gdata chunk failed",
                extra=log_extra(gids=len(chunk), error=str(exc)),
            )
            continue
        for gallery in body.get("gmetadata", []) or []:
            if gallery.get("error") or gallery.get("gid") is None:
                continue
            gid = int(gallery.get("gid"))
            parent = gallery.get("parent") or gallery.get("parent_gid") or ""
            parent_gid = int(parent) if str(parent).isdigit() else None
            result[gid] = {
                "token": gallery.get("token") or "",
                "thumb": html.unescape(gallery.get("thumb", "") or ""),
                "title": html.unescape(gallery.get("title", "") or ""),
                "title_jpn": (
                    html.unescape(gallery["title_jpn"])
                    if gallery.get("title_jpn")
                    else None
                ),
                "category": gallery.get("category") or None,
                "file_count": int(gallery.get("filecount") or 0),
                "file_size": int(gallery.get("filesize") or 0) or None,
                "tags": gallery.get("tags", []) or [],
                "posted": int(gallery.get("posted") or 0),
                "expunged": bool(gallery.get("expunged")),
                "uploader": gallery.get("uploader") or None,
                "rating": float(gallery.get("rating") or 0) or None,
                "parent_gid": parent_gid,
            }
    if failed_chunks and not result and last_error is not None:
        raise last_error
    if failed_chunks:
        logger.warning(
            "ExHentai gdata returned partial metadata",
            extra=log_extra(failed_chunks=failed_chunks, total_chunks=chunk_count),
        )
    return result

async def fetch_gallery_by_category(client, category: str) -> tuple[int, str] | None:
    """Return the first ``(gid, token)`` listed for an ExHentai content category."""
    masks = {
        "doujinshi": 1,
        "manga": 2,
        "artistcg": 4,
        "gamecg": 8,
        "western": 16,
        "non-h": 32,
        "image_set": 64,
        "cosplay": 128,
        "asianporn": 256,
        "misc": 512,
    }
    mask = masks.get(category)
    if mask is None:
        return None
    response = await client._get("/", params={"f_cats": mask})
    match = re.search(r"/g/(\d+)/([0-9a-f]+)/", response.text)
    if not match:
        return None
    return int(match.group(1)), match.group(2)
