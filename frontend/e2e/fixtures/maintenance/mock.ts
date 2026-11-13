import type { Page, Route } from "@playwright/test";
import { sessionEp } from "@/api/auth";
import { notificationsEp } from "@/api/system";
import { galleryThumbEp } from "@/api/galleries";
import {
  crossGidDuplicatesEp,
  duplicateStatusEp,
  favoriteDuplicatesStatusEp,
  ignoreFavoriteDuplicateEp,
  ignoredFavoriteDuplicatesEp,
  libraryDuplicatesEp,
  libraryScanEp,
  refreshCrossGidDuplicatesEp,
  removeFavoritesEp,
  resolveDuplicateEp,
  scanFavoriteDuplicatesEp,
} from "@/api/duplicates";
import {
  expungedGalleriesEp,
  purgeGalleriesEp,
  redownloadExpungedEp,
  restoreGalleriesEp,
  trashGalleriesEp,
} from "@/api/recycle";
import {
  integrityGalleriesEp,
  redownloadGalleryEp,
  scanIntegrityEp,
} from "@/api/integrity";
import {
  updatesDeleteEp,
  updatesIgnoreEp,
  updatesIgnoredEp,
  updatesScanEp,
  updatesStatusEp,
  updatesUnignoreEp,
  updatesUpdateEp,
  updatesEp,
} from "@/api/updates";

/** Prefix shared by every mocked backend route (the `/api` literal itself is allowed). */
const API_ROOT = "/api";

/** Mock cover URLs must point at the real thumbnail endpoint. */
function thumb(gid: number, page = 0): string {
  return galleryThumbEp.path.replace("{id}", String(gid)).replace("{id}", String(page));
}

/** Turn an endpoint pattern like `/api/x/{id}/y` into a matcher for numeric ids. */
function pathMatcher(pattern: string): RegExp {
  const parts = pattern.split(/\{[^}]+\}/g);
  const escaped = parts.map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`^${escaped.join("\\d+")}$`);
}

const RE_THUMB = pathMatcher(galleryThumbEp.path);
const RE_RESOLVE = pathMatcher(resolveDuplicateEp.path);
const RE_DUPLICATE_STATUS = pathMatcher(duplicateStatusEp.path);
const RE_REDOWNLOAD = pathMatcher(redownloadGalleryEp.path);

export interface RecordedRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: Record<string, unknown> | null;
}

export interface MaintenanceMockState {
  requests: RecordedRequest[];
  favoriteScans: number;
  libraryScans: number;
  removals: Array<{ gids: number[]; deleteLocal: boolean }>;
}

const UPDATES = [
  {
    id: 1,
    gallery_id: 11,
    old_gid: 1001,
    new_gid: 2001,
    title: "Updated Alpha",
    favcat: 3,
    favcat_name: "Favorites",
    status: "pending",
    error_message: null,
    detected_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    cover_url: thumb(11),
  },
  {
    id: 2,
    gallery_id: 12,
    old_gid: 1002,
    new_gid: 2002,
    title: "Updated Beta",
    favcat: 1,
    favcat_name: "Reading",
    status: "downloading",
    error_message: null,
    detected_at: "2026-11-02T10:00:00Z",
    updated_at: "2026-11-02T10:00:00Z",
    cover_url: thumb(12),
  },
  {
    id: 3,
    gallery_id: 13,
    old_gid: 1003,
    new_gid: 2003,
    title: "Updated Gamma",
    favcat: 3,
    favcat_name: "Favorites",
    status: "failed",
    error_message: "network timeout",
    detected_at: "2026-11-03T10:00:00Z",
    updated_at: "2026-11-03T10:00:00Z",
    cover_url: thumb(13),
  },
];

const IGNORED_UPDATES = [
  {
    id: 4,
    gallery_id: 14,
    old_gid: 1004,
    new_gid: 2004,
    title: "Ignored Delta",
    favcat: 2,
    favcat_name: "Later",
    status: "ignored",
    error_message: null,
    detected_at: "2026-11-04T10:00:00Z",
    updated_at: "2026-11-04T10:00:00Z",
    cover_url: thumb(14),
  },
];

const LIBRARY_DUPLICATES = [
  {
    gid: 9001,
    status: "open",
    policy: "keep_first",
    winner_path: "/library/alpha",
    copies: [
      {
        key: "copy-a",
        path: "/library/alpha",
        gallery_id: 11,
        storage_type: "folder",
        title: "Alpha Copy",
        display_title: "Alpha Copy",
        page_count: 20,
        file_size: 1024 * 1024 * 30,
        posted_at: "2025-01-02T00:00:00Z",
        is_current: true,
        tags: [{ namespace: "language", name: "chinese", display: "中文" }],
      },
      {
        key: "copy-b",
        path: "/library/alpha.cbz",
        gallery_id: null,
        storage_type: "cbz",
        title: "Alpha CBZ",
        display_title: "Alpha CBZ",
        page_count: 20,
        file_size: 1024 * 1024 * 25,
        posted_at: null,
        is_current: false,
        tags: [],
      },
    ],
  },
  {
    gid: 9002,
    status: "dismissed",
    policy: "manual",
    winner_path: null,
    copies: [
      {
        key: "copy-c",
        path: "/library/beta",
        gallery_id: 12,
        storage_type: "folder",
        title: "Beta Copy",
        display_title: "Beta Copy",
        page_count: 14,
        file_size: 1024 * 1024 * 12,
        posted_at: null,
        is_current: true,
        tags: [],
      },
      {
        key: "copy-d",
        path: "/library/beta.cbr",
        gallery_id: null,
        storage_type: "cbr",
        title: "Beta CBR",
        display_title: "Beta CBR",
        page_count: 14,
        file_size: 1024 * 1024 * 11,
        posted_at: null,
        is_current: false,
        tags: [],
      },
    ],
  },
];

const FAVORITE_DUPLICATES = [
  {
    key: "fav-group-1",
    artist: "artist one",
    items: [
      {
        gid: 3001,
        title: "Favorite Local",
        display_title: "Favorite Local",
        gallery_id: 11,
        favcat: 3,
        file_size: 1024 * 1024 * 20,
        posted_at: "2025-02-01T00:00:00Z",
        tags: [{ namespace: "language", name: "chinese", display: "中文" }],
      },
      {
        gid: 3002,
        title: "Favorite Cloud",
        display_title: "Favorite Cloud",
        gallery_id: null,
        favcat: 2,
        favorited: true,
        token: "abcdef012345",
        url: "https://e-hentai.org/g/3002/abcdef012345/",
        cover_url: thumb(3002),
        file_size: 1024 * 1024 * 18,
        posted_at: "2025-02-02T00:00:00Z",
        tags: [{ namespace: "language", name: "english", display: "English" }],
      },
    ],
  },
];

const IGNORED_FAVORITES = [
  {
    key: "ignored-fav-1",
    title: "Ignored Favorite Group",
    gids: [4001],
    items: [
      {
        gid: 4001,
        title: "Ignored Favorite",
        display_title: "Ignored Favorite",
        gallery_id: null,
        favcat: 1,
        token: "aaaabbbbcccc",
        url: "https://e-hentai.org/g/4001/aaaabbbbcccc/",
        cover_url: thumb(4001),
        file_size: 1024 * 1024 * 9,
      },
    ],
  },
];

const CROSS_GID = [
  {
    key: "xgid-1",
    artist: "artist two",
    items: [
      {
        gid: 5001,
        gallery_id: 11,
        title: "Cross Local",
        display_title: "Cross Local",
        page_count: 22,
        file_size: 1024 * 1024 * 40,
        storage_type: "folder",
      },
      {
        gid: 5002,
        gallery_id: null,
        title: "Cross Cloud",
        display_title: "Cross Cloud",
        url: "javascript:alert(1)",
        favorited: true,
        token: "ddddeeeeffff",
        category: "doujinshi",
        page_count: 22,
        file_size: 1024 * 1024 * 38,
        cover_url: thumb(5002),
      },
    ],
  },
];

/** Tags used to exercise chips / `+N` / namespace tooltips on both pages. */
const RICH_TAGS = [
  { namespace: "female", name: "sole female", display: "单女" },
  { namespace: "male", name: "sole male", display: "单男" },
  { namespace: "artist", name: "artist alpha", display: "画师甲" },
  { namespace: "group", name: "circle beta", display: "社团乙" },
  { namespace: "parody", name: "series gamma", display: "原作丙" },
  { namespace: "language", name: "chinese", display: "中文" },
];

const TRASH = [
  {
    id: 21,
    gid: 7001,
    token: "aaaabbbbcccc",
    title: "Trash One",
    category: "manga",
    page_count: 18,
    cover_url: thumb(21),
    trashed_at: "2026-10-01T00:00:00Z",
    storage_path: "/library/trash-one",
    tags: RICH_TAGS,
    tag_count: RICH_TAGS.length,
  },
  {
    id: 22,
    gid: 7002,
    token: "aaaabbbbcccc",
    title: "Trash Two",
    category: "doujinshi",
    page_count: 24,
    cover_url: thumb(22),
    trashed_at: "2026-10-02T00:00:00Z",
    storage_path: "/library/trash-two",
    tags: [],
    tag_count: 0,
  },
];

const EXPUNGED = [
  {
    id: 31,
    gid: 7101,
    token: "aaaabbbbcccc",
    title: "Expunged One",
    page_count: 30,
    cover_url: thumb(31),
    updated_at: "2026-09-01T00:00:00Z",
    storage_path: "/library/expunged-one",
    tags: RICH_TAGS.slice(0, 2),
    tag_count: 2,
  },
];

const INTEGRITY = [
  {
    id: 41,
    gid: 7201,
    title: "Integrity One",
    page_count: 20,
    actual_pages: 17,
    file_count: 18,
    cover_url: thumb(41),
    storage_path: "/library/integrity-one",
    tags: RICH_TAGS.slice(0, 4),
  },
  {
    id: 42,
    gid: 7202,
    title: "Integrity Two",
    page_count: 12,
    actual_pages: 9,
    file_count: 9,
    cover_url: thumb(42),
    storage_path: "/library/integrity-two",
    tags: [],
  },
];

const SCAN_SUMMARY = {
  running: false,
  started_at: "2026-11-10T08:00:00Z",
  completed_at: "2026-11-10T08:05:00Z",
  scanned: 10,
  total: 12,
  corrupt: 2,
};

const PLACEHOLDER = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="213" viewBox="0 0 160 213">
<rect width="160" height="213" fill="#6b7478"/>
<text x="50%" y="52%" text-anchor="middle" font-family="sans-serif" font-size="16" fill="#f4f1ea">cover</text>
</svg>`;

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function pageOf<T>(items: T[], page: number, pageSize: number) {
  const start = (page - 1) * pageSize;
  return {
    total: items.length,
    page,
    page_size: pageSize,
    items: items.slice(start, start + pageSize),
  };
}

function updateList(state: string) {
  const items =
    state === "failed"
      ? UPDATES.filter((item) => item.status === "failed")
      : state === "pending"
        ? UPDATES.filter((item) => item.status === "pending")
        : state === "downloading"
          ? UPDATES.filter((item) => item.status === "downloading")
          : UPDATES;
  return { total: items.length, page: 1, page_size: 24, state, items };
}

/**
 * Hermetic backend for the maintenance views. Handles every endpoint the four
 * views call, including the image endpoints used by thumbnails.
 */
export interface MaintenanceMockOptions {
  /** Serve an empty integrity list (with the scan summary still present). */
  integrityEmpty?: boolean;
  /** Serve empty recycle lists (both trash and expunged). */
  recycleEmpty?: boolean;
}

export async function installMaintenanceMock(
  page: Page,
  options: MaintenanceMockOptions = {},
): Promise<MaintenanceMockState> {
  const state: MaintenanceMockState = {
    requests: [],
    favoriteScans: 0,
    libraryScans: 0,
    removals: [],
  };

  await page.route(
    (url) => url.pathname.startsWith(`${API_ROOT}/`),
    async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let body: Record<string, unknown> | null = null;
    try {
      body = request.postDataJSON() as Record<string, unknown>;
    } catch {
      body = null;
    }
    state.requests.push({ method, path, query: url.searchParams, body });

    // Real-app routes run behind AppShell, so the auth probe and the topbar
    // notification probe must work here as well (the harness never asks).
    if (path === sessionEp.path && method === "GET") {
      await json(route, {
        authenticated: true,
        auth_required: true,
        must_change_password: false,
        cookie_health: { state: "ok" },
      });
      return;
    }
    if (path === notificationsEp.path && method === "GET") {
      await json(route, { items: [], unread: 0 });
      return;
    }

    if (method === "GET" && RE_THUMB.test(path)) {
      await route.fulfill({ status: 200, contentType: "image/svg+xml", body: PLACEHOLDER });
      return;
    }

    if (path === updatesEp.path && method === "GET") {
      await json(route, updateList(url.searchParams.get("state") ?? "active"));
      return;
    }
    if (path === updatesIgnoredEp.path && method === "GET") {
      await json(route, {
        total: IGNORED_UPDATES.length,
        page: 1,
        page_size: 500,
        state: "ignored",
        items: IGNORED_UPDATES,
      });
      return;
    }
    if (path === updatesStatusEp.path && method === "GET") {
      await json(route, {
        detecting: false,
        last_detected_at: "2026-11-10T08:00:00Z",
        last_run: "2026-11-10T08:00:00Z",
        last_error: null,
        last_found: 3,
        counts: { pending: 1, downloading: 1, failed: 1, ignored: 1 },
      });
      return;
    }
    if (path === updatesScanEp.path && method === "POST") {
      await json(route, { status: "started" }, 202);
      return;
    }
    if (
      method === "POST" &&
      [updatesUpdateEp.path, updatesIgnoreEp.path, updatesUnignoreEp.path, updatesDeleteEp.path].includes(
        path,
      )
    ) {
      const ids = Array.isArray(body?.ids) ? body.ids : [];
      await json(route, path.endsWith("/update") ? { started: ids.length, skipped: 0 } : { ok: true });
      return;
    }

    if (path === libraryScanEp.path && method === "POST") {
      state.libraryScans += 1;
      await json(route, { status: "started" }, 202);
      return;
    }
    if (path === libraryScanEp.path && method === "GET") {
      await json(route, { running: false });
      return;
    }
    if (path === libraryDuplicatesEp.path && method === "GET") {
      await json(route, { groups: LIBRARY_DUPLICATES, count: LIBRARY_DUPLICATES.length });
      return;
    }
    if (RE_RESOLVE.test(path) && method === "POST") {
      await json(route, { groups: LIBRARY_DUPLICATES.slice(1), count: LIBRARY_DUPLICATES.length - 1, failed_paths: [] });
      return;
    }
    if (RE_DUPLICATE_STATUS.test(path) && ["open", "dismissed"].includes(path.split("/").pop() ?? "") && method === "POST") {
      await json(route, { status: path.split("/").pop() });
      return;
    }

    if (path === crossGidDuplicatesEp.path && method === "GET") {
      await json(route, { ready: true, count: CROSS_GID.length, groups: CROSS_GID });
      return;
    }
    if (path === refreshCrossGidDuplicatesEp.path && method === "POST") {
      await json(route, { ready: true, count: CROSS_GID.length, groups: CROSS_GID });
      return;
    }

    if (path === favoriteDuplicatesStatusEp.path && method === "GET") {
      await json(route, {
        running: false,
        stage: "done",
        done: 6,
        total: 6,
        last_error: null,
        groups: FAVORITE_DUPLICATES,
        group_count: FAVORITE_DUPLICATES.length,
        item_count: 2,
        ignored: [],
      });
      return;
    }
    if (path === scanFavoriteDuplicatesEp.path && method === "POST") {
      state.favoriteScans += 1;
      await json(route, { started: true }, 202);
      return;
    }
    if (path === ignoreFavoriteDuplicateEp.path && method === "POST") {
      await json(route, { ok: true, key: String(body?.key ?? "") });
      return;
    }
    if (path === ignoreFavoriteDuplicateEp.path && method === "DELETE") {
      await json(route, { ok: true, key: url.searchParams.get("key") ?? "" });
      return;
    }
    if (path === ignoredFavoriteDuplicatesEp.path && method === "GET") {
      await json(route, IGNORED_FAVORITES);
      return;
    }
    if (path === removeFavoritesEp.path && method === "POST") {
      const gids = Array.isArray(body?.gids) ? (body.gids as number[]) : [];
      const deleteLocal = Boolean(body?.delete_local);
      state.removals.push({ gids, deleteLocal });
      await json(route, {
        gids,
        cloud_ok: true,
        cloud_failed: [],
        successful_gids: gids,
        deleted_local_galleries: deleteLocal ? gids.length : 0,
        failed_deletions: [],
      });
      return;
    }

    if (path === trashGalleriesEp.path && method === "GET") {
      const trash = options.recycleEmpty ? [] : TRASH;
      await json(route, pageOf(trash, Number(url.searchParams.get("page") ?? 1), 24));
      return;
    }
    if (path === expungedGalleriesEp.path && method === "GET") {
      const expunged = options.recycleEmpty ? [] : EXPUNGED;
      await json(route, pageOf(expunged, Number(url.searchParams.get("page") ?? 1), 24));
      return;
    }
    if (path === restoreGalleriesEp.path && method === "POST") {
      const ids = Array.isArray(body?.ids) ? body.ids : [];
      await json(route, { restored: ids.length });
      return;
    }
    if (path === purgeGalleriesEp.path && method === "POST") {
      const ids = Array.isArray(body?.ids) ? body.ids : [];
      await json(route, { purged: ids.length, failed_deletions: [], results: [] });
      return;
    }
    if (path === redownloadExpungedEp.path && method === "POST") {
      const ids = Array.isArray(body?.ids) ? body.ids : [];
      await json(route, { queued: ids.length, skipped_no_gid: 0, skipped_no_token: 0 });
      return;
    }

    if (path === integrityGalleriesEp.path && method === "GET") {
      const integrity = options.integrityEmpty ? [] : INTEGRITY;
      await json(route, {
        ...pageOf(integrity, Number(url.searchParams.get("page") ?? 1), 24),
        magic_scan: SCAN_SUMMARY,
      });
      return;
    }
    if (path === scanIntegrityEp.path && method === "POST") {
      await json(route, SCAN_SUMMARY, 202);
      return;
    }
    if (RE_REDOWNLOAD.test(path) && method === "POST") {
      await json(route, { status: "queued" });
      return;
    }

    await json(route, {});
  });

  return state;
}
