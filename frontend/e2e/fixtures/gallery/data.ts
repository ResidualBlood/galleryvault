import type { GalleryDetail, GalleryPage } from "../../../src/api/gallery";

export const SMALL_GALLERY_ID = 2;
export const LARGE_GALLERY_ID = 1;
/** Only uploader-independent facts: no uploader, no post date, no rating. */
export const SPARSE_GALLERY_ID = 3;

/* `display` is what the backend tag translation service returns; the zh UI
   shows it, every other locale falls back to `name` (DESIGN C07). */
const TAGS = [
  { namespace: "artist", name: "zeta", display: "泽塔" },
  { namespace: "uploader", name: "fixture-uploader", display: null },
  { namespace: "female", name: "heroine", display: "女主角" },
  { namespace: "parody", name: "fixture-series", display: "示例系列" },
  { namespace: "misc", name: "full color", display: "全彩" },
  { namespace: "artist", name: "alpha", display: "阿尔法" },
];

function pages(count: number): GalleryPage[] {
  return Array.from({ length: count }, (_, index) => ({
    index,
    page_index: index,
    name: `${String(index + 1).padStart(4, "0")}.jpg`,
    media_type: "image/jpeg",
  }));
}

function gallery(
  id: number,
  title: string,
  count: number,
  uploader: string,
  overrides: Partial<GalleryDetail> = {},
): GalleryDetail {
  return {
    id,
    gid: 100000 + id,
    token: `token${id}`,
    title,
    title_jpn: `${title}（日本語）`,
    category: id === SMALL_GALLERY_ID ? "manga" : "doujinshi",
    page_count: count,
    file_size: count * 512 * 1024,
    storage_size: count * 512 * 1024,
    uploader,
    posted_at: "2026-11-01T08:30:00Z",
    rating: 4.25,
    image_quality: "original",
    tags: TAGS,
    pages: pages(count),
    ...overrides,
  };
}

export const GALLERIES: Record<number, GalleryDetail> = {
  [SMALL_GALLERY_ID]: gallery(
    SMALL_GALLERY_ID,
    "Small Detail Fixture",
    12,
    "fixture-uploader",
  ),
  [LARGE_GALLERY_ID]: gallery(
    LARGE_GALLERY_ID,
    "Large Virtual Gallery",
    1000,
    "fixture-uploader",
  ),
  [SPARSE_GALLERY_ID]: gallery(
    SPARSE_GALLERY_ID,
    "Sparse Detail Fixture",
    5,
    "",
    { posted_at: null, rating: null, image_quality: null, tags: [] },
  ),
};

export const DEFAULT_PROGRESS: Record<number, number> = {
  [SMALL_GALLERY_ID]: 3,
  [LARGE_GALLERY_ID]: 640,
  [SPARSE_GALLERY_ID]: 0,
};

export function thumbnailSvg(index = 0): string {
  const label =
    index === 0
      ? '<text x="48" y="70" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#f1eee7">COVER</text>'
      : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="128" viewBox="0 0 96 128">
  <rect width="96" height="128" fill="#2f3537"/>
  <rect x="8" y="8" width="80" height="112" fill="#202426"/>
  ${label}
</svg>`;
}
