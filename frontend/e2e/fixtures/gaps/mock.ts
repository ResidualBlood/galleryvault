import type { Page, Route } from "@playwright/test";
import type { OnlineSearchResponse } from "@/api/eh";
import { ehSearchEp, ehStatusEp } from "@/api/eh";
import { previewArchiveEp } from "@/api/archive";
import { createDownloadBatchEp } from "@/api/downloads";
import {
  favoriteCategoriesEp,
  addFavoritesEp,
  downloadSelectedFavoritesEp,
} from "@/api/favorites";
import {
  galleriesEp,
  deleteGalleriesBulkEp,
} from "@/api/galleries";
import { listsEp, savedSearchesEp } from "@/api/library";
import { readerGalleryEp } from "@/api/reader";
import { settingsEp } from "@/api/settings";
import { updatesEp, updatesStatusEp, updatesUpdateEp } from "@/api/updates";

export interface GapsState {
  galleryCalls: URLSearchParams[];
  deleted: Set<number>;
  previews: Array<{ gids?: number[] }>;
  updateBodies: Array<Record<string, unknown>>;
  favoriteAdds: Array<{ items: Array<{ gid: number }> }>;
  favoriteDownloads: Array<Record<string, unknown>>;
  deletedBulk: Array<{ ids: number[]; delete_files?: boolean }>;
  downloadBatches: Array<Record<string, unknown>>;
  favoriteChecks: number[];
  onlineSearches: URLSearchParams[];
  onlineStatusCalls: number;
  archiveQuality: "resample" | "original";
  settingsCalls: number;
  batchFavoriteCloudFailed: Set<number>;
}

function gallery(id: number) {
  return {
    id,
    gid: 100000 + id,
    token: `token-${id}`,
    title: `Library Gallery ${id}`,
    title_english: null,
    title_jpn: null,
    category: "doujinshi",
    page_count: 20 + id,
    cover_url: null,
    tags: [],
    uploader: `uploader-${id}`,
    posted_at: new Date(Date.UTC(2025, 0, id)).toISOString(),
    file_size: 1024 * 1024 * (10 + id),
    storage_size: 1024 * 1024 * (10 + id),
    rating: 4,
    favorite: false,
    favorite_category: null,
    reading_progress: 0,
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

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

const UPDATE_ITEMS = [
  {
    id: 1,
    gallery_id: 11,
    old_gid: 700001,
    new_gid: 900001,
    title: "Updated Alpha",
    favcat: 0,
    favcat_name: "Favorites 0",
    status: "pending",
    cover_url: null,
  },
  {
    id: 2,
    gallery_id: 12,
    old_gid: 700002,
    new_gid: 900002,
    title: "Updated Beta",
    favcat: 0,
    favcat_name: "Favorites 0",
    status: "pending",
    cover_url: null,
  },
];

const FAVORITE_ITEMS = [800001, 800002].map((gid, index) => ({
  favcat: 0,
  gid,
  token: `fav-token-${gid}`,
  title: `Favorite ${gid}`,
  title_jpn: null,
  url: `https://e-hentai.org/g/${gid}/${gid}/`,
  gallery_id: 51 + index,
  category: "doujinshi",
  page_count: 30,
  cover_url: null,
  file_size: null,
  note: null,
  is_local: true,
  tags: [],
}));

export const GAP_ONLINE_ITEMS = [600001, 600002, 600003].map((gid, index) => ({
  gid,
  token: `online-token-${gid}`,
  title: `Online Gap ${index + 1}`,
  url: `https://exhentai.org/g/${gid}/${gid}/`,
  thumb: null,
  category: "doujinshi",
  pages: 12,
  rating: 4,
  in_library: false,
  gallery_id: null,
  favorited: false,
  favcat: null,
  download_status: null,
}));

export const GAP_READER_GALLERY_ID = 77;

/**
 * Mock for the batch-17 gap coverage. Unhandled `/api/**` calls fall through to
 * the shell fixture so the session/notification probes keep working.
 */
export interface GapsOptions {
  /** Value served by GET /api/settings for the archive dialog default. */
  archiveQuality?: "resample" | "original";
}

export async function installGapsMock(
  page: Page,
  options: GapsOptions = {},
): Promise<GapsState> {
  const state: GapsState = {
    galleryCalls: [],
    deleted: new Set(),
    previews: [],
    updateBodies: [],
    favoriteAdds: [],
    favoriteDownloads: [],
    deletedBulk: [],
    downloadBatches: [],
    favoriteChecks: [],
    onlineSearches: [],
    onlineStatusCalls: 0,
    archiveQuality: options.archiveQuality ?? "resample",
    settingsCalls: 0,
    batchFavoriteCloudFailed: new Set(),
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const body = (() => {
      try {
        return request.postDataJSON() as Record<string, unknown>;
      } catch {
        return null;
      }
    })();

    if (path === settingsEp.path && method === "GET") {
      state.settingsCalls += 1;
      await json(route, {
        download_quality: "resample",
        archive_quality: state.archiveQuality,
      });
      return;
    }

    if (path === ehSearchEp.path && method === "GET") {
      state.onlineSearches.push(url.searchParams);
      const response: OnlineSearchResponse = {
        state: "ok",
        items: GAP_ONLINE_ITEMS,
        next: null,
        q: url.searchParams.get("q") ?? "",
      };
      await json(route, response);
      return;
    }

    if (path === ehStatusEp.path && method === "GET") {
      state.onlineStatusCalls += 1;
      await json(route, { items: [] });
      return;
    }

    if (path === createDownloadBatchEp.path && method === "POST") {
      const items = (body?.items as Array<{ gid: number }>) ?? [];
      state.downloadBatches.push(body ?? {});
      await json(route, {
        queued: items.length,
        skipped: 0,
        gone: 0,
        updated: 0,
        failed: 0,
        items: items.map((item) => ({ gid: item.gid, status: "queued" })),
      });
      return;
    }

    if (
      path === readerGalleryEp.path.replace("{id}", String(GAP_READER_GALLERY_ID)) &&
      method === "GET"
    ) {
      await json(route, {
        id: GAP_READER_GALLERY_ID,
        gid: 770001,
        token: "reader-token",
        title: "Animated Reader Fixture",
        category: "manga",
        page_count: 2,
        file_size: 2048,
        favorite: false,
        reading_progress: 0,
        tags: [],
        pages: [
          { index: 0, page_index: 0, name: "001.gif", media_type: "image/gif" },
          { index: 1, page_index: 1, name: "002.jpg", media_type: "image/jpeg" },
        ],
      });
      return;
    }

    if (path === galleriesEp.path && method === "GET") {
      const params = url.searchParams;
      state.galleryCalls.push(params);
      const pageNo = intParam(params, "page", 1);
      const pageSize = intParam(params, "page_size", 24);
      const all = [1, 2, 3, 4]
        .map(gallery)
        .filter((item) => !state.deleted.has(item.id));
      const start = (pageNo - 1) * pageSize;
      await json(route, {
        total: all.length,
        page: pageNo,
        page_size: pageSize,
        q: params.get("q") ?? "",
        tags: params.get("tags") ?? "",
        resolved: false,
        tag_mode: params.get("tag_mode") ?? "and",
        tag_match: params.get("tag_match") ?? "exact",
        order_by: params.get("order_by") ?? "id_desc",
        read_status: params.get("read_status") ?? "all",
        category: params.get("category") ?? "",
        items: all.slice(start, start + pageSize),
      });
      return;
    }

    if (path === deleteGalleriesBulkEp.path && method === "POST") {
      const ids = (body?.ids as number[]) ?? [];
      state.deletedBulk.push({
        ids,
        delete_files: Boolean(body?.delete_files),
      });
      for (const id of ids) state.deleted.add(id);
      await json(route, {
        deleted: ids.length,
        trashed: 0,
        failed_deletions: [],
      });
      return;
    }

    if (path === previewArchiveEp.path && method === "POST") {
      const gids = (body?.gids as number[]) ?? [];
      state.previews.push({ gids });
      await json(route, {
        funds: 5000,
        items: gids.map((gid) => ({
          gid,
          title: `Archive ${gid}`,
          resample_cost: 10,
          resample_size: 1024 * 1024,
          original_cost: 100,
          original_size: 8 * 1024 * 1024,
          resample_available: true,
          original_available: true,
        })),
      });
      return;
    }

    if (path === updatesEp.path && method === "GET") {
      const stateParam = url.searchParams.get("state") ?? "active";
      const items =
        stateParam === "failed" ? [] : UPDATE_ITEMS;
      await json(route, {
        total: items.length,
        page: 1,
        page_size: 50,
        state: stateParam,
        items,
      });
      return;
    }

    if (path === updatesStatusEp.path && method === "GET") {
      await json(route, {
        detecting: false,
        last_detected_at: null,
        last_run: null,
        last_error: null,
        last_found: 0,
        counts: {},
      });
      return;
    }

    if (path === updatesUpdateEp.path && method === "POST") {
      state.updateBodies.push(body ?? {});
      const ids = (body?.ids as number[]) ?? [];
      await json(route, { started: ids.length, skipped: 0 });
      return;
    }

    if (path === favoriteCategoriesEp.path && method === "GET") {
      await json(
        route,
        Array.from({ length: 10 }, (_, favcat) => ({
          favcat,
          name: `Favorites ${favcat}`,
          cloud_count: 10,
          enabled: true,
          mode: "incremental",
        })),
      );
      return;
    }

    if (/\/api\/favorites\/\d+\/items$/.test(path) && method === "GET") {
      const favcat = Number(path.split("/")[3]);
      await json(route, {
        total: FAVORITE_ITEMS.length,
        page: 1,
        page_size: 50,
        state: "all",
        items: FAVORITE_ITEMS.map((item) => ({ ...item, favcat })),
      });
      return;
    }

    if (path === addFavoritesEp.path && method === "POST") {
      // Quick-action adds post a single {gid,…}; the library batch posts items.
      const items =
        (body?.items as Array<{ gid: number }>) ??
        (typeof body?.gid === "number" ? [{ gid: body.gid }] : []);
      state.favoriteAdds.push({ items });
      const cloudFailed = items
        .map((item) => item.gid)
        .filter((gid) => state.batchFavoriteCloudFailed.has(gid));
      const successful = items
        .map((item) => item.gid)
        .filter((gid) => !state.batchFavoriteCloudFailed.has(gid));
      await json(route, {
        cloud_ok: cloudFailed.length === 0,
        cloud_failed: cloudFailed,
        successful_gids: successful,
        local_added: successful.length,
      });
      return;
    }

    const checkMatch = path.match(/^\/api\/favorites\/(\d+)\/check$/);
    if (checkMatch && method === "POST") {
      state.favoriteChecks.push(Number(checkMatch[1]));
      await json(route, { status: "started", favcat: Number(checkMatch[1]) });
      return;
    }

    if (path === downloadSelectedFavoritesEp.path && method === "POST") {
      state.favoriteDownloads.push(body ?? {});
      const gids = (body?.gids as number[]) ?? [];
      await json(route, { queued: gids.length, skipped: 0 });
      return;
    }

    if (path === listsEp.path && method === "GET") {
      await json(route, { items: [{ id: 3, name: "Filter List", count: 2 }] });
      return;
    }

    if (path === savedSearchesEp.path && method === "GET") {
      await json(route, { items: [] });
      return;
    }

    await route.fallback();
  });

  return state;
}
