import type { Page, Route } from "@playwright/test";

export interface LibraryMockState {
  total: number;
  requests: URLSearchParams[];
}

export interface InstallOptions {
  total?: number;
}

const CATEGORIES = ["doujinshi", "manga", "artistcg", "gamecg", "western", "non-h"];

function gallery(id: number) {
  return {
    id,
    gid: 100000 + id,
    token: `token-${id}`,
    title: `Gallery ${String(id).padStart(4, "0")}`,
    title_english: null,
    title_jpn: null,
    storage_type: "ehviewer_dir",
    category: CATEGORIES[id % CATEGORIES.length],
    page_count: (id % 120) + 10,
    cover_url: null,
    tags: [
      { namespace: "language", name: "chinese", display: "中文" },
      { namespace: "artist", name: `artist-${id % 20}`, display: `画师 ${id % 20}` },
      { namespace: "female", name: "sole female", display: "单体女性" },
    ],
    uploader: `uploader-${id % 12}`,
    posted_at: new Date(Date.UTC(2025, 0, 1 + (id % 300))).toISOString(),
    file_size: 1024 * 1024 * (10 + (id % 90)),
    storage_size: 1024 * 1024 * (10 + (id % 90)),
    rating: 2 + (id % 8) / 2,
    favorite: id % 7 === 0,
    favorite_category: id % 7 === 0 ? id % 10 : null,
    reading_progress: id % 5 === 0 ? 3 : 0,
    expunged: false,
    image_quality: "resample",
    local_rating: null,
    local_note: null,
  };
}

function intParam(params: URLSearchParams, key: string, fallback: number): number {
  const parsed = Number.parseInt(params.get(key) ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function listPage(state: LibraryMockState, params: URLSearchParams) {
  const page = intParam(params, "page", 1);
  const pageSize = intParam(params, "page_size", 24);
  const start = (page - 1) * pageSize;
  const ids: number[] = [];
  for (let id = start + 1; id <= Math.min(state.total, start + pageSize); id += 1) {
    ids.push(id);
  }
  // A title sort reverses the fixture order, making the request observable.
  const ordered = params.get("order_by") === "title_asc" ? [...ids].reverse() : ids;
  return {
    total: state.total,
    page,
    page_size: pageSize,
    q: params.get("q") ?? "",
    tags: params.get("tags") ?? "",
    resolved: false,
    tag_mode: params.get("tag_mode") ?? "and",
    tag_match: params.get("tag_match") ?? "exact",
    order_by: params.get("order_by") ?? "id_desc",
    read_status: params.get("read_status") ?? "all",
    category: params.get("category") ?? "",
    items: ordered.map(gallery),
  };
}

// Neutral placeholder cover so light/dark screenshots stay readable.
const COVER_SVG = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="213" viewBox="0 0 160 213">' +
    '<rect width="160" height="213" fill="#6b7478"/>' +
    '<path d="M48 92h64M48 110h64M48 128h44" stroke="#f1eee7" stroke-width="4" stroke-linecap="round"/>' +
    '</svg>',
);

async function fulfillJson(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/**
 * Deterministic mocked list backend for @library. Registered after the shell
 * fixture, so Playwright runs these handlers first.
 */
export async function installLibraryMock(
  page: Page,
  options: InstallOptions = {},
): Promise<LibraryMockState> {
  const state: LibraryMockState = {
    total: options.total ?? 5000,
    requests: [],
  };

  await page.route("**/api/galleries**", async (route) => {
    const url = new URL(route.request().url());
    const params = url.searchParams;
    if (url.pathname.endsWith("/galleries/random")) {
      await fulfillJson(route, { id: 7 });
      return;
    }
    if (/\/thumb\/\d+$/.test(url.pathname)) {
      await route.fulfill({ status: 200, contentType: "image/svg+xml", body: COVER_SVG });
      return;
    }
    if (url.pathname.endsWith("/galleries")) {
      state.requests.push(params);
      await fulfillJson(route, listPage(state, params));
      return;
    }
    await fulfillJson(route, {});
  });

  await page.route("**/api/history**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.endsWith("/history")) {
      await fulfillJson(route, {});
      return;
    }
    await fulfillJson(route, {
      total: 3,
      page: 1,
      page_size: 8,
      items: [42, 43, 44].map((id, index) => ({
        gallery_id: id,
        current_page: index + 2,
        total_pages: 40 + index * 5,
        last_read_at: new Date(Date.UTC(2025, 5, 1 + index)).toISOString(),
        title: `Gallery ${id}`,
        display_title: `Continue ${id}`,
        raw_title: `Gallery ${id}`,
        title_jpn: null,
        gid: 100000 + id,
        category: "doujinshi",
        url: `/galleries/${id}`,
      })),
    });
  });

  await page.route("**/api/tags/search**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.endsWith("/tags/search")) {
      await fulfillJson(route, {});
      return;
    }
    const q = url.searchParams.get("q") ?? "";
    await fulfillJson(route, {
      total: q ? 1 : 4,
      page: 1,
      page_size: 8,
      facets: [
        { namespace: "language", total: 120 },
        { namespace: "artist", total: 80 },
        { namespace: "female", total: 300 },
        { namespace: "male", total: 90 },
      ],
      items: q
        ? [
            {
              namespace: "language",
              name: "chinese",
              display: "中文",
              usage_count: 120,
            },
          ]
        : [],
    });
  });

  return state;
}
