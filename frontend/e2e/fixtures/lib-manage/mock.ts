import type { Page, Route } from "@playwright/test";

export interface SavedSearchRecord {
  id: string;
  name: string;
  query: Record<string, string>;
}

export interface ListRecord {
  id: number;
  name: string;
  count: number;
}

export interface SeriesMemberFixture {
  id: number | null;
  gallery_id: number | null;
  is_local: boolean;
  gid: number | null;
  favcat: number | null;
  token: string | null;
  url: string | null;
  title: string;
  category: string;
  page_count: number;
  cover_url: string | null;
  tags: Array<{ namespace: string; name: string; display?: string }>;
}

export interface SeriesGroupFixture {
  id: number;
  name: string;
  match_key: string | null;
  name_manual: boolean;
  count: number;
  created_at: string | null;
  galleries: SeriesMemberFixture[];
}

export interface LibManageState {
  savedSearches: SavedSearchRecord[];
  lists: ListRecord[];
  galleryListIds: number[];
  deletedBulk: Array<{ ids: number[]; delete_files?: boolean }>;
  deletedFiltered: Array<Record<string, unknown>>;
  deleteFilteredCalls: number;
  filteredMatched: number;
  favoritesCategoriesRequests: number;
  favoriteAdds: Array<{ items: Array<{ gid: number; token?: string }>; target_favcat: number }>;
  localPatches: Array<Record<string, unknown>>;
  favoriteNotes: Array<Record<string, unknown>>;
  originalDownloads: Array<Record<string, unknown>>;
  syncTags: number;
  favoriteDownloads: Array<{ favcat: number; gids: number[]; quality?: string }>;
  redownloads: number[];
  galleryDeletes: Array<{ id: number; delete_files: string | null }>;
  seriesCreates: string[];
  seriesRenames: Array<{ id: number; name: string }>;
  seriesDeletes: number[];
  seriesRebuilds: number;
  cloudItemsAdded: Array<{ id: number; gids: number[] }>;
  cloudItemsRemoved: Array<{ id: number; gids: number[] }>;
  localItemsRemoved: Array<{ id: number; gallery_ids: number[] }>;
  tagReloads: number;
  tagSyncStarts: number;
  tagQueries: URLSearchParams[];
}

const API_ROOT = "/" + "api";
const api = (suffix: string): string => `${API_ROOT}${suffix}`;

const SERIES: SeriesGroupFixture[] = [
  {
    id: 41,
    name: "Alpha Collection",
    match_key: null,
    name_manual: true,
    count: 2,
    created_at: "2026-01-02T00:00:00Z",
    galleries: [
      {
        id: 11,
        gallery_id: 11,
        is_local: true,
        gid: 100011,
        favcat: null,
        token: "tok-11",
        url: "https://e-hentai.org/g/100011/tok-11/",
        title: "Alpha Local One",
        category: "doujinshi",
        page_count: 42,
        cover_url: api("/galleries/11/thumb/0"),
        tags: [{ namespace: "artist", name: "alpha" }],
      },
      {
        id: null,
        gallery_id: null,
        is_local: false,
        gid: 200011,
        favcat: 3,
        token: "tok-c11",
        url: "https://e-hentai.org/g/200011/tok-c11/",
        title: "Alpha Cloud One",
        category: "manga",
        page_count: 31,
        cover_url: null,
        tags: [],
      },
    ],
  },
  {
    id: 42,
    name: "Beta Collection",
    match_key: "beta",
    name_manual: false,
    count: 2,
    created_at: "2026-01-03T00:00:00Z",
    galleries: [
      {
        id: 12,
        gallery_id: 12,
        is_local: true,
        gid: 100012,
        favcat: null,
        token: "tok-12",
        url: "https://e-hentai.org/g/100012/tok-12/",
        title: "Beta Local One",
        category: "artistcg",
        page_count: 26,
        cover_url: api("/galleries/12/thumb/0"),
        tags: [],
      },
      {
        id: null,
        gallery_id: null,
        is_local: false,
        gid: 200012,
        favcat: 4,
        token: "tok-c12",
        url: "https://e-hentai.org/g/200012/tok-c12/",
        title: "Beta Cloud One",
        category: "western",
        page_count: 22,
        cover_url: null,
        tags: [],
      },
    ],
  },
  {
    id: 43,
    name: "Gamma Collection",
    match_key: "gamma",
    name_manual: false,
    count: 2,
    created_at: "2026-01-04T00:00:00Z",
    galleries: [
      {
        id: 13,
        gallery_id: 13,
        is_local: true,
        gid: 100013,
        favcat: null,
        token: "tok-13",
        url: "https://e-hentai.org/g/100013/tok-13/",
        title: "Gamma Local One",
        category: "gamecg",
        page_count: 18,
        cover_url: api("/galleries/13/thumb/0"),
        tags: [],
      },
      {
        id: null,
        gallery_id: null,
        is_local: false,
        gid: 200013,
        favcat: 3,
        token: "tok-c13",
        url: "https://e-hentai.org/g/200013/tok-c13/",
        title: "Gamma Cloud One",
        category: "misc",
        page_count: 15,
        cover_url: null,
        tags: [],
      },
    ],
  },
];

const TAG_ITEMS = [
  { namespace: "artist", name: "alpha", display: "Alpha", usage_count: 90 },
  { namespace: "artist", name: "beta", display: "Beta", usage_count: 60 },
  { namespace: "language", name: "chinese", display: "中文", usage_count: 120 },
  { namespace: "female", name: "sole female", display: "单体女性", usage_count: 300 },
  { namespace: "male", name: "sole male", display: "单体男性", usage_count: 210 },
  { namespace: "parody", name: "dragon", display: "龙", usage_count: 45 },
];

function galleryDetail(id: number) {
  return {
    id,
    gid: 200000 + id,
    token: `token-${id}`,
    title: `Gallery ${id}`,
    title_english: null,
    title_jpn: null,
    storage_type: "ehviewer_dir",
    category: "doujinshi",
    page_count: 12,
    file_size: 1024 * 1024 * 40,
    storage_size: 1024 * 1024 * 40,
    uploader: "tester",
    posted_at: "2025-11-01T00:00:00Z",
    rating: 4,
    favorite: true,
    favorite_category: 1,
    reading_progress: 2,
    expunged: false,
    image_quality: "resample",
    local_rating: 4,
    local_note: "local note",
    storage_path: "/library/gallery-5",
    eh_url: "https://e-hentai.org/g/200005/token-5/",
    exhentai_url: null,
    tags: [
      { namespace: "language", name: "chinese", display: "中文" },
      { namespace: "artist", name: "alpha", display: "Alpha" },
      { namespace: "local", name: "favourite", display: "favourite" },
    ],
    pages: Array.from({ length: 12 }, (_, index) => ({
      index,
      name: `page-${index + 1}`,
      media_type: "image/jpeg",
      thumb_url: `${API_ROOT}/galleries/${id}/thumb/${index}`,
    })),
  };
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function int(value: string | null, fallback = 0): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Mock backend for the library-management batch (saved searches, lists,
 * batch/filtered delete, series, tags, gallery manage actions).
 *
 * Registered *after* the shared shell/library fixtures; unknown paths fall
 * through so those keep serving browse/library data.
 */
export async function installLibManageMock(page: Page): Promise<LibManageState> {
  const state: LibManageState = {
    savedSearches: [
      {
        id: "saved-1",
        name: "中文未读",
        query: { tags: "language:chinese", read_status: "unread" },
      },
    ],
    lists: [
      { id: 1, name: "待读", count: 3 },
      { id: 2, name: "经典", count: 1 },
    ],
    galleryListIds: [1],
    deletedBulk: [],
    deletedFiltered: [],
    deleteFilteredCalls: 0,
    filteredMatched: 250,
    favoritesCategoriesRequests: 0,
    favoriteAdds: [],
    localPatches: [],
    favoriteNotes: [],
    originalDownloads: [],
    syncTags: 0,
    favoriteDownloads: [],
    redownloads: [],
    galleryDeletes: [],
    seriesCreates: [],
    seriesRenames: [],
    seriesDeletes: [],
    seriesRebuilds: 0,
    cloudItemsAdded: [],
    cloudItemsRemoved: [],
    localItemsRemoved: [],
    tagReloads: 0,
    tagSyncStarts: 0,
    tagQueries: [],
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const body = (() => {
      try {
        return request.postDataJSON();
      } catch {
        return null;
      }
    })() as Record<string, unknown> | null;

    /* saved searches */
    if (path === api("/saved-searches") && method === "GET") {
      await json(route, { items: state.savedSearches });
      return;
    }
    if (path === api("/saved-searches") && method === "POST") {
      const record: SavedSearchRecord = {
        id: `saved-${state.savedSearches.length + 1}`,
        name: String(body?.name ?? ""),
        query: (body?.query as Record<string, string>) ?? {},
      };
      state.savedSearches = [...state.savedSearches, record];
      await json(route, record, 201);
      return;
    }
    if (new RegExp(`^${API_ROOT}/saved-searches/[^/]+$`).test(path) && method === "DELETE") {
      const id = path.split("/").pop() ?? "";
      state.savedSearches = state.savedSearches.filter((item) => item.id !== id);
      await json(route, { deleted: true, id });
      return;
    }

    /* lists */
    if (path === api("/lists") && method === "GET") {
      await json(route, { items: state.lists });
      return;
    }
    if (path === api("/lists") && method === "POST") {
      const record: ListRecord = {
        id: state.lists.length + 1,
        name: String(body?.name ?? ""),
        count: 0,
      };
      state.lists = [...state.lists, record];
      await json(route, record, 201);
      return;
    }
    if (new RegExp(`^${API_ROOT}/lists/\\d+/items$`).test(path) && method === "POST") {
      const listId = Number(path.split("/")[3]);
      const ids = (body?.gallery_ids as number[]) ?? [];
      state.lists = state.lists.map((item) =>
        item.id === listId ? { ...item, count: item.count + ids.length } : item,
      );
      await json(route, { id: listId, added: ids.length });
      return;
    }
    if (new RegExp(`^${API_ROOT}/lists/\\d+/items/remove$`).test(path) && method === "POST") {
      const listId = Number(path.split("/")[3]);
      const ids = (body?.gallery_ids as number[]) ?? [];
      state.lists = state.lists.map((item) =>
        item.id === listId ? { ...item, count: Math.max(0, item.count - ids.length) } : item,
      );
      await json(route, { id: listId, removed: ids.length });
      return;
    }
    if (new RegExp(`^${API_ROOT}/galleries/\\d+/lists$`).test(path) && method === "GET") {
      const items = state.lists
        .filter((item) => state.galleryListIds.includes(item.id))
        .map((item) => ({ id: item.id, name: item.name }));
      await json(route, { items });
      return;
    }

    /* bulk + filtered delete */
    if (path === api("/galleries/delete-bulk") && method === "POST") {
      const ids = (body?.ids as number[]) ?? [];
      state.deletedBulk.push({
        ids,
        delete_files: Boolean(body?.delete_files),
      });
      await json(route, {
        deleted: ids.length,
        trashed: 0,
        failed_deletions: [],
        results: ids.map((id) => ({ id, db_removed: true })),
      });
      return;
    }
    if (path === api("/galleries/delete-filtered") && method === "POST") {
      state.deleteFilteredCalls += 1;
      state.deletedFiltered.push(body ?? {});
      if (!body?.confirm) {
        await json(
          route,
          {
            detail: {
              code: "CONFIRM_REQUIRED",
              matched: state.filteredMatched,
              threshold: 200,
              message: `matched ${state.filteredMatched} galleries exceeds confirm threshold 200`,
            },
          },
          409,
        );
        return;
      }
      await json(route, {
        deleted: Number(body?.match_count ?? state.filteredMatched),
        trashed: 0,
        failed_deletions: [],
      });
      return;
    }

    /* favourite categories + batch add */
    if (path === api("/favorites/categories") && method === "GET") {
      state.favoritesCategoriesRequests += 1;
      await json(
        route,
        Array.from({ length: 10 }, (_, favcat) => ({
          favcat,
          name: favcat === 0 ? "Favorites 0" : `Favorites ${favcat}`,
          cloud_count: 10 - favcat,
          enabled: true,
          mode: "incremental",
        })),
      );
      return;
    }
    if (path === api("/favorites/add") && method === "POST") {
      const items = (body?.items as Array<{ gid: number; token?: string }>) ?? [];
      state.favoriteAdds.push({
        items,
        target_favcat: Number(body?.target_favcat ?? 0),
      });
      await json(route, {
        cloud_ok: true,
        cloud_failed: [],
        successful_gids: items.map((item) => item.gid),
        local_added: items.length,
      });
      return;
    }
    if (path === api("/favorites/note") && method === "POST") {
      state.favoriteNotes.push(body ?? {});
      await json(route, {
        gid: Number(body?.gid ?? 0),
        cloud_ok: true,
        local_updated: 1,
        note: body?.note ?? "",
      });
      return;
    }
    if (path === api("/favorites/download-selected") && method === "POST") {
      state.favoriteDownloads.push({
        favcat: Number(body?.favcat ?? 0),
        gids: (body?.gids as number[]) ?? [],
        quality: typeof body?.quality === "string" ? body.quality : undefined,
      });
      await json(route, { queued: (body?.gids as number[])?.length ?? 0, skipped: 0 });
      return;
    }

    /* tags */
    if (path === api("/tags/search") && method === "GET") {
      state.tagQueries.push(url.searchParams);
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const namespace = url.searchParams.get("namespace") ?? "";
      let items = TAG_ITEMS;
      if (q) {
        items = items.filter(
          (item) => item.name.includes(q) || (item.display ?? "").toLowerCase().includes(q),
        );
      }
      if (namespace) items = items.filter((item) => item.namespace === namespace);
      await json(route, {
        total: url.searchParams.get("page_size") === "1" ? items.length : items.length,
        page: 1,
        page_size: int(url.searchParams.get("page_size"), 100),
        facets:
          url.searchParams.get("page_size") === "1"
            ? [
                { namespace: "language", total: 120 },
                { namespace: "artist", total: 80 },
                { namespace: "female", total: 300 },
              ]
            : [],
        items,
      });
      return;
    }
    if (path === api("/tags/search/reload") && method === "POST") {
      state.tagReloads += 1;
      await json(route, { accepted: true, ok: true, last_error: null }, 202);
      return;
    }
    if (path === api("/tag-sync/start") && method === "POST") {
      state.tagSyncStarts += 1;
      await json(route, { status: "started", queued: 4 }, 202);
      return;
    }

    /* series */
    if (path === api("/series") && method === "GET") {
      const page = Math.max(1, int(url.searchParams.get("page"), 1));
      const pageSize = Math.max(1, int(url.searchParams.get("page_size"), 25));
      const start = (page - 1) * pageSize;
      await json(route, {
        items: SERIES.slice(start, start + pageSize),
        total: SERIES.length,
        page,
        page_size: pageSize,
      });
      return;
    }
    if (path === api("/series") && method === "POST") {
      state.seriesCreates.push(String(body?.name ?? ""));
      await json(
        route,
        {
          id: 99,
          name: String(body?.name ?? ""),
          match_key: null,
          name_manual: true,
          count: 0,
          created_at: null,
          galleries: [],
        },
        201,
      );
      return;
    }
    if (path === api("/series/rebuild") && method === "POST") {
      state.seriesRebuilds += 1;
      await json(route, { created: 2, merged: 1 });
      return;
    }
    if (new RegExp(`^${API_ROOT}/series/\\d+$`).test(path) && method === "PATCH") {
      const id = Number(path.split("/")[3]);
      state.seriesRenames.push({ id, name: String(body?.name ?? "") });
      await json(route, { id, name: String(body?.name ?? ""), galleries: [] });
      return;
    }
    if (new RegExp(`^${API_ROOT}/series/\\d+$`).test(path) && method === "DELETE") {
      state.seriesDeletes.push(Number(path.split("/")[3]));
      await json(route, { deleted: true });
      return;
    }
    if (new RegExp(`^${API_ROOT}/series/\\d+/cloud-candidates$`).test(path) && method === "GET") {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const items = [
        { gid: 300001, title: "Candidate Dragon", thumb: null, token: "c1", favcat: 1 },
        { gid: 300002, title: "Candidate Castle", thumb: null, token: "c2", favcat: 2 },
      ].filter((item) => !q || item.title.toLowerCase().includes(q));
      await json(route, { items });
      return;
    }
    if (new RegExp(`^${API_ROOT}/series/\\d+/cloud-items$`).test(path) && method === "POST") {
      state.cloudItemsAdded.push({
        id: Number(path.split("/")[3]),
        gids: (body?.gids as number[]) ?? [],
      });
      await json(route, { id: Number(path.split("/")[3]), added_local: 0, added_cloud: 2, skipped: 0 });
      return;
    }
    if (new RegExp(`^${API_ROOT}/series/\\d+/cloud-items/remove$`).test(path) && method === "POST") {
      state.cloudItemsRemoved.push({
        id: Number(path.split("/")[3]),
        gids: (body?.gids as number[]) ?? [],
      });
      await json(route, { id: Number(path.split("/")[3]), removed: 1 });
      return;
    }
    if (new RegExp(`^${API_ROOT}/series/\\d+/items/remove$`).test(path) && method === "POST") {
      state.localItemsRemoved.push({
        id: Number(path.split("/")[3]),
        gallery_ids: (body?.gallery_ids as number[]) ?? [],
      });
      await json(route, { id: Number(path.split("/")[3]), removed: 1 });
      return;
    }

    /* gallery detail + manage actions */
    const galleryMatch = path.match(new RegExp(`^${API_ROOT}/galleries/(\\d+)(/.*)?$`));
    if (galleryMatch) {
      const id = Number(galleryMatch[1]);
      const suffix = galleryMatch[2] ?? "";
      if (suffix === "" && method === "GET") {
        await json(route, galleryDetail(id));
        return;
      }
      if (suffix === "/progress" && method === "GET") {
        await json(route, { gallery_id: id, current_page: 2, total_pages: 12, updated_at: null });
        return;
      }
      if (suffix === "/favorite" && method === "GET") {
        await json(route, {
          gid: 200000 + id,
          token: `token-${id}`,
          favorite: true,
          favcats: [1],
          favcat_names: [{ favcat: 1, name: "Favorites 1" }],
          note: "cloud note",
        });
        return;
      }
      if (suffix === "/local" && method === "PATCH") {
        state.localPatches.push({ id, ...(body ?? {}) });
        await json(route, { id, ...(body ?? {}) });
        return;
      }
      if (suffix === "" && method === "DELETE") {
        state.galleryDeletes.push({ id, delete_files: url.searchParams.get("delete_files") });
        await json(route, { deleted: true });
        return;
      }
      if (suffix === "/download-original" && method === "POST") {
        state.originalDownloads.push({ id, ...(body ?? {}) });
        await json(route, { status: "queued", queued: true });
        return;
      }
      if (suffix === "/redownload" && method === "POST") {
        state.redownloads.push(id);
        await json(route, { status: "queued", queued: true });
        return;
      }
      if (suffix === "/sync-tags" && method === "POST") {
        state.syncTags += 1;
        await json(route, { source: "network", count: 17 });
        return;
      }
      if (/^\/thumb\/\d+$/.test(suffix)) {
        await route.fulfill({
          status: 200,
          contentType: "image/svg+xml",
          body:
            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="160">' +
            '<rect width="120" height="160" fill="#6b7478"/></svg>',
        });
        return;
      }
    }

    await route.fallback();
  });

  return state;
}
