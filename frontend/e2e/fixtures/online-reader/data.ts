import type { OnlineDetailResponse } from "../../../src/api/eh";
import type { OnlineHistoryResponse, OnlineProgress } from "../../../src/api/eh-reader";

export const READER_GID = 900001;
export const READER_TOKEN = "tok900001";
export const READER_PAGES = 10;
export const READER_TITLE = "Online Reader Fixture";

export function pageSvg(index: number, width = 800, height = 1200): string {
  const label = `Online page ${index + 1}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f4f1ea"/>
  <rect x="24" y="24" width="${width - 48}" height="${height - 48}" rx="12" fill="none" stroke="#8a8177" stroke-width="2"/>
  <text x="50%" y="48%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 9)}" fill="#1c1a17">${label}</text>
  <text x="50%" y="57%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 24)}" fill="#55504a">GalleryVault direct-source fixture</text>
</svg>`;
}

export function detailResponse(): OnlineDetailResponse {
  return {
    state: "ok",
    gallery: {
      gid: READER_GID,
      token: READER_TOKEN,
      title: READER_TITLE,
      title_jpn: "オンライン リーダー",
      category: "manga",
      uploader: "fixture-uploader",
      posted: "2026-10-01 12:00",
      pages: READER_PAGES,
      rating: 4.5,
      file_size: 123_456_789,
      thumb: "https://ehgt.org/reader-cover.svg",
      tags: [{ namespace: "language", name: "chinese" }],
      newer: null,
      parent_gid: null,
      in_library: false,
      gallery_id: null,
      favorited: false,
      favcat: null,
      download: null,
    },
  };
}

export function progressPayload(page: number, total = READER_PAGES): OnlineProgress {
  return {
    page,
    total_pages: total,
    updated_at: "2026-11-12T10:00:00Z",
  };
}

export function historyResponse(count = 3): OnlineHistoryResponse {
  return {
    page: 1,
    page_size: 20,
    total: count,
    items: Array.from({ length: count }, (_, index) => ({
      gid: 910000 + index,
      token: `tok${910000 + index}`,
      title: `Continue Fixture ${index + 1}`,
      thumb: `https://ehgt.org/history-${index + 1}.svg`,
      page: 3 + index,
      total_pages: 12,
      updated_at: "2026-11-12T09:00:00Z",
    })),
  };
}
