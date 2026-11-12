import type { Page, Route } from "@playwright/test";

export interface MockRequest {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
}

export interface SettingsMockOptions {
  cookieState?: string;
  securityPassword?: string;
  settings?: Record<string, unknown>;
}

export interface SettingsMock {
  requests: MockRequest[];
  posts: MockRequest[];
  settings: Record<string, unknown>;
  notificationItems: Array<Record<string, unknown>>;
  archives: { running: boolean; done: number; total: number };
}

const BASE_SETTINGS: Record<string, unknown> = {
  library_roots: ["/library"],
  library_root_warnings: [],
  cold_storage_root: "/cold",
  archive_roots: ["/cold"],
  auto_archive_downloads: false,
  archive_delete_source: false,
  exhentai_base_url: "https://exhentai.org",
  exhentai_cookie_names: ["ipb_member_id", "ipb_pass_hash"],
  exhentai_cookie_configured: true,
  http_proxy: null,
  socks5_proxy: null,
  download_root: "/downloads",
  download_concurrency: 2,
  page_concurrency: 4,
  download_quality: "resample",
  download_title: "japanese",
  archive_quality: "resample",
  favorites_archive_enabled: false,
  favorites_archive_max_pages: 0,
  archive_fallback_pages: true,
  use_hah: true,
  image_download_timeout_seconds: 120,
  image_slow_warmup_seconds: 30,
  image_min_speed_kb_s: 10,
  title_display: "japanese",
  download_max_retries: 10,
  favorites_categories: [0, 3],
  download_favorites_enabled: false,
  favorites_poll_interval_minutes: 720,
  telegram_bot_configured: true,
  telegram_chat_ids: ["-100123"],
  telegram_allowed_user_ids: [],
  telegram_notify_level: "summary",
  telegram_notify_lang: "zh",
  auto_sync_tags: true,
  tag_sync_interval_seconds: 1.5,
  tag_sync_concurrency: 4,
  tag_translation_update_interval_minutes: 720,
  generate_thumbnails: true,
  duplicate_policy: "keep_first",
  thumbnail_cache_dir: "/cache/thumbs",
  auth_required: true,
  auth_hash_configured: true,
  must_change_password: false,
  online_reader_concurrency: 3,
  online_cache_max_mb: 512,
};

const SECURITY_KEYS = ["auth_required", "trusted_proxies", "download_root", "library_roots"];

const FAVORITES = Array.from({ length: 10 }, (_, favcat) => ({
  favcat,
  name: favcat === 0 ? "Favorites" : `Folder ${favcat}`,
  cloud_count: favcat === 0 ? 12 : 0,
  enabled: favcat === 0 || favcat === 3,
  mode: "incremental",
}));

const LOG_ENTRIES = [
  {
    id: 3,
    time: "2026-11-12T21:00:03+08:00",
    level: "ERROR",
    logger: "galleryvault.scan",
    message: "scan failed for gallery 4242",
    context: { gallery_id: 4242 },
    exception: null,
  },
  {
    id: 2,
    time: "2026-11-12T21:00:02+08:00",
    level: "WARNING",
    logger: "galleryvault.eh",
    message: "image limit low",
    context: { remaining: 120 },
    exception: null,
  },
  {
    id: 1,
    time: "2026-11-12T21:00:01+08:00",
    level: "INFO",
    logger: "galleryvault.app",
    message: "application started",
    context: null,
    exception: null,
  },
];

async function bodyOf(route: Route): Promise<Record<string, unknown> | null> {
  try {
    const raw = route.request().postData();
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function json(route: Route, status: number, data: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(data),
  });
}

export async function mockSettingsBackend(
  page: Page,
  options: SettingsMockOptions = {},
): Promise<SettingsMock> {
  const settings = { ...BASE_SETTINGS, ...(options.settings ?? {}) };
  const requests: MockRequest[] = [];
  const posts: MockRequest[] = [];
  let tokenConfigured = false;
  let unread = 2;
  let notifications = [
    {
      id: 2,
      kind: "archive",
      title: "归档完成",
      detail: "12 本画廊已转入冷存储",
      created_at: "2026-11-12T20:00:00+08:00",
      read: false,
    },
    {
      id: 1,
      kind: "scan",
      title: "扫描完成",
      detail: "新增 3 本画廊",
      created_at: "2026-11-12T19:00:00+08:00",
      read: false,
    },
  ];
  const archives = { running: false, done: 4, total: 10 };
  let paused = false;
  let scanRunning = false;
  const cookieState = options.cookieState ?? "ok";

  await page.route("**/*", async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const path = new URL(request.url()).pathname;
    // Vite serves source modules from /src/api/*.ts; only intercept the real API.
    if (!path.startsWith("/api/")) {
      await route.continue();
      return;
    }
    const body = await bodyOf(route);
    const record: MockRequest = { method, path, body };
    requests.push(record);
    if (method !== "GET") posts.push(record);

    if (path === "/api/settings" && method === "GET") {
      await json(route, 200, settings);
      return;
    }
    if (path === "/api/settings" && method === "POST") {
      const payload = body ?? {};
      const changedSecurity = SECURITY_KEYS.filter((key) => key in payload);
      const password = typeof payload.current_password === "string" ? payload.current_password : "";
      if (changedSecurity.length && !password) {
        await json(route, 428, {
          detail: "Security confirmation required",
          keys: changedSecurity,
        });
        return;
      }
      for (const [key, value] of Object.entries(payload)) {
        if (key === "current_password") continue;
        settings[key] = value;
      }
      await json(route, 200, settings);
      return;
    }
    if (path === "/api/settings/cookie-health") {
      await json(route, 200, {
        state: cookieState,
        message: cookieState === "not_logged_in" ? "Cookie 已失效" : "",
      });
      return;
    }
    if (path === "/api/settings/exhentai/test") {
      await json(route, 200, { status: "ok", message: "登录正常" });
      return;
    }
    if (path === "/api/pause" && method === "GET") {
      await json(route, 200, { paused });
      return;
    }
    if (path === "/api/pause" && method === "POST") {
      paused = Boolean(body?.paused);
      await json(route, 200, { paused });
      return;
    }
    if (path === "/api/scan" && method === "GET") {
      await json(route, 200, { running: scanRunning });
      return;
    }
    if (path === "/api/scan" && method === "POST") {
      scanRunning = true;
      await json(route, 202, { status: "started" });
      return;
    }
    if (path === "/api/system/storage") {
      await json(route, 200, {
        library: { path: "/library", bytes: 8589934592, gallery_count: 120, computing: false },
        cold: { path: "/cold", bytes: 42949672960, gallery_count: 400, computing: false },
        downloads: { path: "/downloads", bytes: 1073741824, computing: false },
        cache: { path: "/cache", bytes: 536870912, thumbnail_count: 8000, computing: false },
        largest: [
          { id: 11, title: "Largest Gallery A", storage_size: 3221225472, file_count: 210 },
          { id: 12, title: "Largest Gallery B", storage_size: 2147483648, file_count: 180 },
        ],
      });
      return;
    }
    if (path === "/api/thumbs/status") {
      await json(route, 200, { running: false, completed_at: "2026-11-12T20:00:00Z", succeeded: 1200, failed: 3 });
      return;
    }
    if (path === "/api/thumbs/generate") {
      await json(route, 200, { queued: 3 });
      return;
    }
    if (path === "/api/telegram/test") {
      await json(route, 200, { ok: true, results: [] });
      return;
    }
    if (path === "/api/tags/search/status") {
      await json(route, 200, { ok: true, entries: 1234, last_error: null, interval_minutes: 720 });
      return;
    }
    if (path === "/api/tags/search/reload") {
      await json(route, 200, { ok: true });
      return;
    }
    if (path === "/api/tag-sync/start") {
      await json(route, 202, { queued: 2 });
      return;
    }
    if (path === "/api/tag-sync/repair-categories") {
      await json(route, 200, { repaired: 3, total: 4 });
      return;
    }
    if (path === "/api/auth/api-token" && method === "GET") {
      await json(route, 200, {
        configured: tokenConfigured,
        created_at: tokenConfigured ? "2026-11-12T20:00:00+08:00" : null,
      });
      return;
    }
    if (path === "/api/auth/api-token" && method === "POST") {
      tokenConfigured = true;
      await json(route, 200, { token: "gvt_TEST_ONLY_TOKEN_9f3c" });
      return;
    }
    if (path === "/api/auth/api-token" && method === "DELETE") {
      tokenConfigured = false;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/api/auth/change-password") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/api/favorites/categories") {
      await json(route, 200, FAVORITES);
      return;
    }
    if (path === "/api/favorites/check-all") {
      await json(route, 202, { status: "started" });
      return;
    }
    if (path === "/api/onboarding/status") {
      await json(route, 200, {
        password_default: false,
        exhentai_configured: true,
        library_count: 12,
      });
      return;
    }
    if (path === "/api/galleries") {
      await json(route, 200, {
        total: 2,
        page: 1,
        page_size: 4,
        items: [
          { id: 11, gid: 101, token: "aaa", title: "Recent One", category: "doujinshi", page_count: 24, cover_url: null, tags: [] },
          { id: 12, gid: 102, token: "bbb", title: "Recent Two", category: "manga", page_count: 40, cover_url: null, tags: [] },
        ],
      });
      return;
    }
    if (path === "/api/notifications" && method === "GET") {
      await json(route, 200, { items: notifications, unread_count: unread });
      return;
    }
    if (path === "/api/notifications/read") {
      notifications = notifications.map((item) => ({ ...item, read: true }));
      unread = 0;
      await json(route, 200, { items: notifications, unread_count: unread });
      return;
    }
    if (path === "/api/notifications/clear") {
      notifications = [];
      unread = 0;
      await json(route, 200, { items: [], unread_count: 0 });
      return;
    }
    if (path === "/api/logs") {
      await json(route, 200, {
        running: [
          {
            task: "scan",
            started_at: "2026-11-12T20:30:00+08:00",
            done: 30,
            total: 120,
            stage: "scanning",
            cancellable: true,
          },
        ],
        finished: [
          {
            task: "archive",
            status: "success",
            started_at: "2026-11-12T20:00:00+08:00",
            completed_at: "2026-11-12T20:10:00+08:00",
            done: 10,
            total: 10,
          },
        ],
      });
      return;
    }
    if (/^\/api\/logs\/[^/]+\/cancel$/.test(path)) {
      await json(route, 202, { status: "cancelling" });
      return;
    }
    if (path === "/api/logs/archive/cancel") {
      archives.running = false;
      await json(route, 202, { status: "cancelling" });
      return;
    }
    if (path === "/api/system/logs" && method === "GET") {
      await json(route, 200, {
        level: "INFO",
        log_mode: "memory",
        log_file: null,
        logs: LOG_ENTRIES,
      });
      return;
    }
    if (path === "/api/system/logs" && method === "DELETE") {
      await json(route, 200, { status: "cleared" });
      return;
    }
    if (path === "/api/system/logs/level") {
      await json(route, 200, { level: String(body?.level ?? "INFO") });
      return;
    }
    if (path === "/api/system/logs/download") {
      await route.fulfill({
        status: 200,
        contentType: "text/plain",
        body: "2026-11-12 INFO galleryvault.app application started\n",
      });
      return;
    }
    if (path === "/api/archive" && method === "GET") {
      await json(route, 200, {
        running: archives.running,
        done: archives.done,
        total: archives.total,
        skipped: 1,
        failed: 0,
        last_error: null,
        started_at: archives.running ? "2026-11-12T20:00:00+08:00" : null,
        completed_at: archives.running ? null : "2026-11-12T20:10:00+08:00",
      });
      return;
    }
    if (path === "/api/archive" && method === "POST") {
      archives.running = true;
      await json(route, 202, { status: "started" });
      return;
    }
    if (path === "/api/archives/preview") {
      await json(route, 200, {
        funds: 12345,
        items: [
          {
            gid: 101,
            title: "Preview One",
            resample_cost: 20,
            resample_size: 52428800,
            original_cost: 60,
            original_size: 209715200,
            resample_available: true,
            original_available: true,
          },
          {
            gid: 102,
            title: "Preview Two",
            resample_cost: 15,
            resample_size: 31457280,
            original_cost: null,
            original_size: null,
            resample_available: true,
            original_available: false,
          },
        ],
      });
      return;
    }
    if (path === "/api/system/purge-archived-sources") {
      await json(route, 202, { status: "started" });
      return;
    }
    if (path === "/api/auth/session") {
      await json(route, 200, { authenticated: true, auth_required: true, must_change_password: false });
      return;
    }
    await json(route, 200, {});
  });

  return {
    requests,
    posts,
    settings,
    get notificationItems() {
      return notifications;
    },
    archives,
  };
}
