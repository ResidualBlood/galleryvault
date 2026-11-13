import type {
  OnlineDetailResponse,
  OnlinePreviewPage,
  OnlineSearchItem,
  OnlineSearchResponse,
  OnlineTag,
  OnlineThumb,
} from "../../../src/api/eh";

export const LIST_GID = 900001;
export const LIST_TOKEN = "tok900001";
export const NEWER_GID = 900002;
export const NEWER_TOKEN = "tok900002";
export const LOCAL_GALLERY_ID = 42;

export const PAGE_CURSOR = "1-2";

const CATEGORIES = ["doujinshi", "manga", "artistcg", "image_set"] as const;

/** Tags the list-page HTML exposes (no extra EH request). */
const LIST_TAGS: OnlineTag[] = [
  { namespace: "female", name: "big breasts", display: "巨乳" },
  { namespace: "artist", name: "fixture-artist", display: "夹具画师" },
  { namespace: "parody", name: "fixture-series", display: "夹具系列" },
  { namespace: "character", name: "heroine", display: "女主角" },
  { namespace: "group", name: "fixture-group", display: "夹具社团" },
  { namespace: "language", name: "chinese", display: "中文" },
];

/** One row deliberately has no tag node (minimal list mode). */
const EMPTY_TAGS: OnlineTag[] = [];

export function searchItem(index: number): OnlineSearchItem {
  const gid = 910000 + index;
  return {
    gid,
    token: `tok${gid}`,
    title: `Online Fixture ${String(index).padStart(2, "0")}`,
    url: `https://exhentai.org/g/${gid}/tok${gid}/`,
    thumb: `https://ehgt.org/thumb-${index}.svg`,
    category: CATEGORIES[index % CATEGORIES.length],
    pages: 10 + index,
    rating: 3 + (index % 3) * 0.5,
    tags: index === 2 ? EMPTY_TAGS : LIST_TAGS,
    posted: 1761985800 + index * 3600,
    uploader: "fixture-uploader",
    in_library: index === 4,
    gallery_id: index === 4 ? LOCAL_GALLERY_ID : null,
    favorited: index === 6,
    favcat: index === 6 ? 2 : null,
    download_status: index === 2 ? "downloading" : index === 7 ? "pending" : null,
  };
}

const FIRST_PAGE = Array.from({ length: 12 }, (_, index) => searchItem(index + 1));
const SECOND_PAGE = Array.from({ length: 6 }, (_, index) => searchItem(index + 13));

export function searchResponse(query: URLSearchParams): OnlineSearchResponse {
  const q = (query.get("q") ?? "").trim();
  if (q === "__auth__") {
    return { state: "not_logged_in", items: [], next: null, q };
  }
  if (q === "__banned__") {
    return { state: "banned", items: [], next: null, q };
  }
  if (q === "__challenge__") {
    return { state: "challenge", items: [], next: null, q };
  }
  if (q) {
    return {
      state: "ok",
      items: [{ ...searchItem(1), title: `Search Match: ${q}` }],
      next: null,
      q,
    };
  }
  if (query.get("next") === PAGE_CURSOR) {
    return { state: "ok", items: SECOND_PAGE, next: null, q: "" };
  }
  return { state: "ok", items: FIRST_PAGE, next: PAGE_CURSOR, q: "" };
}

const TAGS: OnlineTag[] = [
  { namespace: "artist", name: "fixture-artist" },
  { namespace: "female", name: "heroine" },
  { namespace: "parody", name: "fixture-series" },
  { namespace: "language", name: "chinese" },
  { namespace: "misc", name: "full color" },
];

const SPRITE_URL = "https://ehgt.org/sprite.svg";
const SPRITE_WIDTH = 200;
const SPRITE_HEIGHT = 280;
const PER_PAGE = 20;

function thumbFor(index: number): OnlineThumb | null {
  // Two thumbs intentionally omit the sprite so the page-number placeholder
  // path is exercised by both the mock and the real component.
  if (index === 1 || index === 18 || index === 25) return null;
  return {
    url: SPRITE_URL,
    x: (index % 5) * SPRITE_WIDTH,
    y: Math.floor((index % 20) / 5) * SPRITE_HEIGHT,
    w: SPRITE_WIDTH,
    h: SPRITE_HEIGHT,
  };
}

export function pagesResponse(gid: number, _token: string, p: number): OnlinePreviewPage {
  const total = gid === NEWER_GID ? 12 : 32;
  const start = p * PER_PAGE;
  const count = Math.max(0, Math.min(PER_PAGE, total - start));
  return {
    state: "ok",
    p,
    per_page: PER_PAGE,
    total,
    items: Array.from({ length: count }, (_, offset) => {
      const index = start + offset;
      return { index, thumb: thumbFor(index) };
    }),
  };
}

export function detailResponse(gid: number, token: string): OnlineDetailResponse {
  if (gid === NEWER_GID && token === NEWER_TOKEN) {
    return {
      state: "ok",
      gallery: {
        gid,
        token,
        title: "Online Detail Fixture (newer)",
        title_jpn: "オンライン詳細",
        category: "manga",
        uploader: "fixture-uploader",
        posted: "2026-11-01T08:30:00Z",
        pages: 12,
        rating: 4.75,
        file_size: 12 * 512 * 1024,
        thumb: "https://ehgt.org/cover-newer.svg",
        tags: TAGS,
        newer: null,
        parent_gid: null,
        in_library: true,
        gallery_id: LOCAL_GALLERY_ID,
        favorited: true,
        favcat: 2,
        download: null,
      },
    };
  }
  // Every list card opens the same fixture detail (the row gid/token are kept)
  // so the list → detail → back flow can be exercised from any card.
  return {
    state: "ok",
    gallery: {
      gid,
      token,
      title: "Online Detail Fixture",
      title_jpn: "オンライン詳細フィクスチャ",
      category: "image_set",
      uploader: "fixture-uploader",
      posted: "2026-11-01T08:30:00Z",
      pages: 32,
      rating: 4.25,
      file_size: 32 * 512 * 1024,
      thumb: "https://ehgt.org/cover.svg",
      tags: TAGS,
      newer: { gid: NEWER_GID, token: NEWER_TOKEN },
      parent_gid: null,
      in_library: false,
      gallery_id: null,
      favorited: false,
      favcat: null,
      download: null,
    },
  };
}

export function thumbSvg(): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="128" viewBox="0 0 96 128">
  <rect width="96" height="128" fill="#2f3537"/>
  <rect x="8" y="8" width="80" height="112" fill="#202426"/>
</svg>`;
}

export function spriteSvg(): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1120" viewBox="0 0 1000 1120">
  <rect width="1000" height="1120" fill="#2f3537"/>
  <rect x="0" y="0" width="200" height="280" fill="#3a3a30"/>
  <rect x="200" y="0" width="200" height="280" fill="#23413c"/>
  <rect x="400" y="0" width="200" height="280" fill="#5b3d00"/>
</svg>`;
}
