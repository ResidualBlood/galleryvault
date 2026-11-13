import type { Page, Route } from "@playwright/test";
import {
  checkAllFavoritesEp,
  checkFavoriteCategoryEp,
  downloadMissingFavoritesEp,
  downloadSelectedFavoritesEp,
  favoriteCategoriesEp,
  favoriteCheckStatusEp,
  favoriteItemsEp,
  moveFavoritesEp,
  removeFavoritesEp,
  syncFavoriteCategoriesEp,
} from "@/api/favorites";
import {
  clearSuccessfulDownloadsEp,
  createDownloadBatchEp,
  downloadsEp,
  pauseEp,
  quotaEp,
  retryAllDownloadsEp,
} from "@/api/downloads";
import {
  clearAllProgressEp,
  clearHistoryEp,
  clearGalleryProgressEp,
  historyEp,
} from "@/api/history";
import { saveSettingsEp } from "@/api/settings";

export interface MockWrite {
  method: string;
  path: string;
  body: unknown;
  csrf: string;
}

export interface FavDlMockState {
  writes: MockWrite[];
  favoriteItemRequests: URLSearchParams[];
  downloadRequests: URLSearchParams[];
  historyRequests: URLSearchParams[];
  paused: boolean;
}

interface MockOptions {
  totalFavorites?: number;
  totalHistory?: number;
  /** Legacy DB rows can carry a display-only mode; the real backend rejects it on save. */
  legacyFavoriteMode?: boolean;
}

/** Mirrors the backend validation in app/routers/settings.py. */
const ALLOWED_FAVORITE_MODES = new Set(["monitor_only", "incremental", "force"]);

const CATEGORIES = [
  {
    favcat: 0,
    name: "Favourites 0",
    enabled: true,
    mode: "incremental",
    poll_interval_minutes: 720,
    cloud_count: 128,
    local_count: 96,
    cloud_size: 14_000_000_000,
    local_size: 9_500_000_000,
  },
  {
    favcat: 1,
    name: "Doujinshi",
    enabled: true,
    mode: "monitor_only",
    poll_interval_minutes: 360,
    cloud_count: 64,
    local_count: 41,
    cloud_size: 8_200_000_000,
    local_size: 4_100_000_000,
  },
  {
    favcat: 2,
    name: "Manga",
    enabled: false,
    mode: "force",
    poll_interval_minutes: 1440,
    cloud_count: 23,
    local_count: 12,
    cloud_size: 3_400_000_000,
    local_size: 1_700_000_000,
  },
];

const DOWNLOAD_TASKS = [
  {
    id: 1,
    gid: 800001,
    title: "Sunset Sketchbook",
    status: "downloading",
    retry_count: 0,
    max_retries: 10,
    current_page: 12,
    total_pages: 40,
    error_message: null,
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_error: null,
    archive_fallback: false,
    speed: 1_572_864,
    eta_seconds: 95,
  },
  {
    id: 2,
    gid: 800002,
    title: "Night Market Diaries",
    status: "pending",
    retry_count: 0,
    max_retries: 10,
    current_page: 0,
    total_pages: null,
    error_message: null,
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_error: null,
    archive_fallback: false,
  },
  {
    id: 3,
    gid: 800003,
    title: "Archive Collection Vol. 3",
    status: "success",
    retry_count: 0,
    max_retries: 10,
    current_page: 120,
    total_pages: 120,
    error_message: null,
    mode: "favorite_archive",
    quality: "original",
    archive_status: "ok",
    archive_error: null,
    archive_fallback: false,
  },
  {
    id: 4,
    gid: 800004,
    title: "Gone Gallery",
    status: "failed",
    retry_count: 3,
    max_retries: 10,
    current_page: 0,
    total_pages: null,
    error_message: "GalleryGoneError: deleted or not found",
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_error: null,
    archive_fallback: false,
  },
  {
    id: 5,
    gid: 800005,
    title: "Cancelled Download",
    status: "cancelled",
    retry_count: 1,
    max_retries: 10,
    current_page: 4,
    total_pages: 30,
    error_message: null,
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_error: null,
    archive_fallback: false,
  },
  {
    id: 6,
    gid: 800006,
    title: "Finished Doujinshi",
    status: "success",
    retry_count: 0,
    max_retries: 10,
    current_page: 24,
    total_pages: 24,
    error_message: null,
    mode: "gallery",
    quality: "original",
    archive_status: null,
    archive_error: null,
    archive_fallback: false,
  },
];

/**
 * 16x21 PNG covers. The shared GalleryCard only accepts real image payloads
 * (base64 png/jpeg/gif/webp or http paths), so the fixture ships tiny PNGs
 * instead of the old inline SVG data URL.
 */
const COVERS = [
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAVCAIAAADAXPmFAAAAH0lEQVR42mMoSAojCTGMaiBGg4eVHkloVMOohgHTAABn5RuQqvjj3gAAAABJRU5ErkJggg==",
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAVCAIAAADAXPmFAAAAH0lEQVR42mMISCoiCTGMaiBGg4aVF0loVMOohgHTAACLYBZQElAn+wAAAABJRU5ErkJggg==",
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAVCAIAAADAXPmFAAAAH0lEQVR42mOIKYgiCTGMaiBGg4mHEUloVMOohgHTAAABihjwmwkNyQAAAABJRU5ErkJggg==",
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAVCAIAAADAXPmFAAAAH0lEQVR42mMoiisjCTGMaiBGg5eZH0loVMOohgHTAABnlkLwWkn4FQAAAABJRU5ErkJggg==",
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAVCAIAAADAXPmFAAAAH0lEQVR42mMoi0ogCTGMaiBGg5+RBUloVMOohgHTAAB+ICYQVg3A5gAAAABJRU5ErkJggg==",
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAVCAIAAADAXPmFAAAAH0lEQVR42mPIywohCTGMaiBGg5uTDkloVMOohgHTAAD1myDQAPAXEQAAAABJRU5ErkJggg==",
];

function cover(index: number): string {
  return COVERS[index % COVERS.length];
}

function favoriteItem(index: number, state: string) {
  const isLocal = state === "local" ? true : state === "cloud" ? false : index % 2 === 1;
  const gid = 5000 + index;
  return {
    favcat: 1,
    gid,
    token: `token${gid.toString(16)}`,
    title: `Favourite Gallery ${String(index).padStart(2, "0")}`,
    title_jpn: null,
    url: `https://e-hentai.org/g/${gid}/token${gid.toString(16)}/`,
    gallery_id: isLocal ? 1000 + index : null,
    category: ["doujinshi", "manga", "artistcg", "gamecg"][index % 4],
    page_count: 18 + index,
    filecount: 18 + index,
    cover_url: cover(index),
    cover_data: null,
    file_size: 18_000_000 + index * 1_250_000,
    filesize: 18_000_000 + index * 1_250_000,
    first_seen_at: "2025-10-01T10:00:00Z",
    is_local: isLocal,
    note: index % 5 === 0 ? "Read again later" : null,
    tags: [
      { namespace: "language", name: "chinese", display: "中文" },
      { namespace: "female", name: "sole female", display: "单体女性" },
      { namespace: "artist", name: `artist-${index % 6}`, display: `画师 ${index % 6}` },
    ],
  };
}

function historyEntry(index: number) {
  return {
    gallery_id: 1000 + index,
    current_page: 3 + index,
    total_pages: 24 + index,
    last_read_at: new Date(Date.UTC(2025, 9, 20 - index, 12, 30)).toISOString(),
    title: `History Gallery ${String(index).padStart(2, "0")}`,
    display_title: `History Gallery ${String(index).padStart(2, "0")}`,
    raw_title: `History Gallery ${String(index).padStart(2, "0")}`,
    title_jpn: null,
    gid: 7000 + index,
    category: ["doujinshi", "manga", "artistcg"][index % 3],
    url: `/galleries/${1000 + index}`,
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function idFromTemplate(template: string, path: string): number | null {
  const [prefix, suffix = ""] = template.split("{id}");
  if (!path.startsWith(prefix) || !path.endsWith(suffix)) return null;
  const raw = path.slice(prefix.length, path.length - suffix.length);
  if (!/^\d+$/.test(raw)) return null;
  return Number.parseInt(raw, 10);
}

function write(route: Route, path: string, body: unknown): MockWrite {
  return {
    method: route.request().method(),
    path,
    body,
    csrf: route.request().headers()["x-csrf-token"] ?? "",
  };
}

function bodyJson(route: Route): unknown {
  try {
    const raw = route.request().postData();
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Deterministic backend for @fav-dl. Registered after the shell fixture so it
 * runs first; unknown paths fall back to the generic mock.
 */
export async function mockFavDlBackend(
  page: Page,
  options: MockOptions = {},
): Promise<FavDlMockState> {
  const totalFavorites = options.totalFavorites ?? 40;
  const totalHistory = options.totalHistory ?? 12;
  const categories = options.legacyFavoriteMode
    ? CATEGORIES.map((item) => (item.favcat === 0 ? { ...item, mode: "gallery" } : item))
    : CATEGORIES;
  const state: FavDlMockState = {
    writes: [],
    favoriteItemRequests: [],
    downloadRequests: [],
    historyRequests: [],
    paused: false,
  };

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    /* --------------------------------------------------------- favorites */
    if (method === "GET" && path === favoriteCategoriesEp.path) {
      await fulfillJson(route, categories);
      return;
    }
    if (method === "GET" && path === favoriteCheckStatusEp.path) {
      await fulfillJson(route, {
        running: true,
        categories: {
          "0": { running: true, done: 96, total: 128 },
          "1": { running: true, done: 12, total: 64 },
        },
        last_error: null,
        started_at: "2025-11-12T10:00:00Z",
        completed_at: null,
      });
      return;
    }
    if (method === "GET" && path === favoriteItemsEp.path.replace("{id}", "1")) {
      state.favoriteItemRequests.push(url.searchParams);
      const pageNo = Number.parseInt(url.searchParams.get("page") ?? "1", 10) || 1;
      const pageSize = Number.parseInt(url.searchParams.get("page_size") ?? "24", 10) || 24;
      const stateFilter = url.searchParams.get("state") ?? "all";
      const start = (pageNo - 1) * pageSize;
      const items = [];
      for (let index = start; index < Math.min(totalFavorites, start + pageSize); index += 1) {
        items.push(favoriteItem(index, stateFilter));
      }
      await fulfillJson(route, {
        total: totalFavorites,
        page: pageNo,
        page_size: pageSize,
        state: stateFilter,
        items,
      });
      return;
    }
    if (method === "POST") {
      const checkId = idFromTemplate(checkFavoriteCategoryEp.path, path);
      if (checkId !== null) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, { status: "started", favcat: checkId });
        return;
      }
      if (path === syncFavoriteCategoriesEp.path) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, { status: "started" });
        return;
      }
      if (path === checkAllFavoritesEp.path) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, { status: "started", favcats: [0, 1, 2] });
        return;
      }
      if (path === downloadMissingFavoritesEp.path) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, { status: "started", favcats: [0, 1, 2] });
        return;
      }
      if (path === downloadSelectedFavoritesEp.path) {
        const body = bodyJson(route) as { gids?: number[] } | null;
        state.writes.push(write(route, path, body));
        await fulfillJson(route, {
          queued: body?.gids?.length ?? 0,
          skipped: 0,
        });
        return;
      }
      if (path === moveFavoritesEp.path) {
        const body = bodyJson(route) as { gids?: number[]; target_favcat?: number } | null;
        const gids = body?.gids ?? [];
        state.writes.push(write(route, path, body));
        await fulfillJson(route, {
          gids,
          target_favcat: body?.target_favcat ?? 0,
          cloud_ok: true,
          cloud_failed: [],
          successful_gids: gids,
          local_moved: gids.length,
        });
        return;
      }
      if (path === removeFavoritesEp.path) {
        const body = bodyJson(route) as { gids?: number[] } | null;
        const gids = body?.gids ?? [];
        state.writes.push(write(route, path, body));
        await fulfillJson(route, {
          gids,
          cloud_ok: true,
          cloud_failed: [],
          successful_gids: gids,
          local_removed: gids.length,
        });
        return;
      }
      if (path === saveSettingsEp.path) {
        const body = bodyJson(route) as
          | { favorites?: Array<Record<string, unknown>> }
          | null;
        state.writes.push(write(route, path, body));
        const favorites = body?.favorites;
        const invalid =
          Array.isArray(favorites) &&
          favorites.some(
            (item) =>
              !item ||
              !ALLOWED_FAVORITE_MODES.has(String(item.mode ?? "")),
          );
        if (invalid) {
          await fulfillJson(route, { detail: "invalid favorites configuration" }, 422);
          return;
        }
        await fulfillJson(route, { ok: true });
        return;
      }

      /* --------------------------------------------------------- downloads */
      if (path === createDownloadBatchEp.path) {
        const body = bodyJson(route) as { items?: unknown[] } | null;
        state.writes.push(write(route, path, body));
        const count = body?.items?.length ?? 0;
        await fulfillJson(route, {
          queued: count,
          skipped: 0,
          gone: 0,
          updated: 0,
          failed: 0,
          items: [],
        });
        return;
      }
      if (path === clearSuccessfulDownloadsEp.path) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, { deleted: 2 });
        return;
      }
      if (path === retryAllDownloadsEp.path) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, { retried_count: 2, count: 2, task_ids: [2, 4] });
        return;
      }
      if (path === pauseEp.path) {
        const body = bodyJson(route) as { paused?: boolean } | null;
        state.paused = Boolean(body?.paused);
        state.writes.push(write(route, path, body));
        await fulfillJson(route, { paused: state.paused });
        return;
      }
      if (/\/(?:cancel|retry)$/.test(path)) {
        state.writes.push(write(route, path, bodyJson(route)));
        await fulfillJson(route, {});
        return;
      }
    }

    if (method === "DELETE") {
      if (path.startsWith(`${downloadsEp.path}/`)) {
        state.writes.push(write(route, path, null));
        await route.fulfill({ status: 204, body: "" });
        return;
      }
      if (path === clearHistoryEp.path) {
        state.writes.push(write(route, path, null));
        await route.fulfill({ status: 204, body: "" });
        return;
      }
      if (path === clearAllProgressEp.path) {
        state.writes.push(write(route, path, null));
        await route.fulfill({ status: 204, body: "" });
        return;
      }
      if (idFromTemplate(clearGalleryProgressEp.path, path) !== null) {
        state.writes.push(write(route, path, null));
        await route.fulfill({ status: 204, body: "" });
        return;
      }
    }

    /* ------------------------------------------------------------ reads */
    if (method === "GET" && path === downloadsEp.path) {
      state.downloadRequests.push(url.searchParams);
      const status = url.searchParams.get("status");
      const filtered =
        status && status !== "all"
          ? DOWNLOAD_TASKS.filter((task) => task.status === status)
          : DOWNLOAD_TASKS;
      const pageNo = Number.parseInt(url.searchParams.get("page") ?? "1", 10) || 1;
      const pageSize = Number.parseInt(url.searchParams.get("page_size") ?? "24", 10) || 24;
      const start = (pageNo - 1) * pageSize;
      await fulfillJson(route, {
        total: filtered.length,
        page: pageNo,
        page_size: pageSize,
        items: filtered.slice(start, start + pageSize),
      });
      return;
    }
    if (method === "GET" && path === quotaEp.path) {
      await fulfillJson(route, {
        gp: 12_345,
        image_limit: { current: 86, limit: 100 },
        image_limits: { current: 86, limit: 100 },
        checked_at: "2025-11-12T10:30:00Z",
        error: null,
        cached: true,
      });
      return;
    }
    if (method === "GET" && path === pauseEp.path) {
      await fulfillJson(route, { paused: state.paused });
      return;
    }
    if (method === "GET" && path === historyEp.path) {
      state.historyRequests.push(url.searchParams);
      const pageNo = Number.parseInt(url.searchParams.get("page") ?? "1", 10) || 1;
      const pageSize = Number.parseInt(url.searchParams.get("page_size") ?? "24", 10) || 24;
      const start = (pageNo - 1) * pageSize;
      const items = [];
      for (let index = start; index < Math.min(totalHistory, start + pageSize); index += 1) {
        items.push(historyEntry(index));
      }
      await fulfillJson(route, {
        total: totalHistory,
        page: pageNo,
        page_size: pageSize,
        items,
      });
      return;
    }

    await route.fallback();
  });

  return state;
}
