/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import {
  expect,
  test as base,
  type APIRequestContext,
  type BrowserContext,
  type Page,
  type PlaywrightWorkerArgs,
} from "@playwright/test";
import { REAL_BASE_URL, REAL_STORAGE_STATE, requireRealPassword } from "./storage";

/**
 * Shared real-environment harness for the C3 parity gate.
 *
 * Writers do not run these specs; the tester runs them against
 * `/mnt/Exhentai/docker-compose.yml` (:8200). The password is only read from
 * `GV_E2E_PASSWORD`; a missing value is a hard failure (never a skip), so a
 * misconfigured CI job cannot silently produce a green gate.
 */
export const BASE_URL = REAL_BASE_URL;
export { requireRealPassword as requirePassword };
export const SHOT_DIR =
  process.env.GV_SHOTS || "/tmp/opencode/gv-frontend-rewrite/shots/real-b7/parity";

export interface GalleryRow {
  id: number;
  gid: number | null;
  token: string | null;
  title: string;
  page_count: number;
  favorite?: boolean;
  favorite_category?: number | null;
}

export interface GalleryListResponse {
  items: GalleryRow[];
  total: number;
}

export interface JsonApi {
  get<T = unknown>(path: string): Promise<T>;
  post<T = unknown>(path: string, body?: unknown): Promise<T>;
  put<T = unknown>(path: string, body?: unknown): Promise<T>;
  patch<T = unknown>(path: string, body?: unknown): Promise<T>;
  del<T = unknown>(path: string): Promise<T>;
}

export interface App {
  page: Page;
  context: BrowserContext;
  api: JsonApi;
  /** Screenshot to `$GV_SHOTS/<id>.png` (checked by the C3 report). */
  shot(id: string, options?: { fullPage?: boolean }): Promise<void>;
}

export function uniqueName(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

export async function screenshot(
  page: Page,
  id: string,
  options: { fullPage?: boolean } = {},
): Promise<void> {
  mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({
    path: join(SHOT_DIR, `${id}.png`),
    fullPage: options.fullPage ?? true,
  });
}

async function csrfToken(context: BrowserContext): Promise<string> {
  const cookies = await context.cookies();
  return cookies.find((cookie) => cookie.name === "galleryvault_csrf")?.value ?? "";
}

function jsonApi(context: BrowserContext): JsonApi {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {};
    if (method !== "GET") {
      const token = await csrfToken(context);
      if (token) headers["X-CSRF-Token"] = token;
    }
    const response = await context.request.fetch(path, {
      method,
      headers,
      data: body,
      failOnStatusCode: false,
    });
    if (!response.ok()) {
      throw new Error(`${method} ${path} -> ${response.status()} ${await response.text()}`);
    }
    if (response.status() === 204) return null as T;
    return (await response.json()) as T;
  }
  return {
    get: (path) => call("GET", path),
    post: (path, body) => call("POST", path, body ?? {}),
    put: (path, body) => call("PUT", path, body ?? {}),
    patch: (path, body) => call("PATCH", path, body ?? {}),
    del: (path) => call("DELETE", path),
  };
}

/** Sign in through the real form endpoint and fail loudly if the session is not usable. */
export async function apiLogin(context: BrowserContext): Promise<void> {
  const password = requireRealPassword();
  const login = await context.request.post("/login", {
    form: { password },
    failOnStatusCode: false,
  });
  if (!login.ok()) {
    throw new Error(`POST /login failed with ${login.status()}`);
  }
  const session = await context.request.get("/api/auth/session");
  if (!session.ok()) {
    throw new Error(`GET /api/auth/session failed with ${session.status()}`);
  }
  const body = (await session.json()) as { authenticated?: boolean };
  if (!body.authenticated) {
    throw new Error("real E2E login did not produce an authenticated session");
  }
}

/**
 * Reuse the session captured by global-setup. Only a genuinely expired/absent
 * session triggers POST /login, so nginx's 10r/m login limit is not at risk.
 */
export async function ensureSession(context: BrowserContext): Promise<void> {
  const session = await context.request.get("/api/auth/session", {
    failOnStatusCode: false,
  });
  if (session.ok()) {
    const body = (await session.json().catch(() => ({}))) as { authenticated?: boolean };
    if (body.authenticated) return;
  }
  await apiLogin(context);
}

export async function firstGallery(api: JsonApi): Promise<GalleryRow | null> {
  const data = await api.get<GalleryListResponse>(
    "/api/galleries?page_size=1&order_by=id_desc",
  );
  return Array.isArray(data.items) && data.items.length ? data.items[0] : null;
}

export async function galleryTotal(api: JsonApi): Promise<number> {
  const data = await api.get<GalleryListResponse>("/api/galleries?page_size=1");
  return Number(data.total) || 0;
}

export function annotateUnverified(description: string): void {
  base.info().annotations.push({ type: "unverified", description });
}

export const test = base.extend<{ app: App }>({
  app: async ({ page, context }, use) => {
    await ensureSession(context);
    await page.goto("/");
    await expect(page.getByTestId("content")).toBeVisible({ timeout: 20_000 });
    await use({
      page,
      context,
      api: jsonApi(context),
      shot: (id, options) => screenshot(page, id, options),
    });
  },
});

export { expect };

/** Shared API request context for tests that need a sample before opening the UI. */
export async function newApiContext(
  playwright: PlaywrightWorkerArgs["playwright"],
): Promise<APIRequestContext> {
  const context = await playwright.request.newContext({
    baseURL: BASE_URL,
    storageState: REAL_STORAGE_STATE,
  });
  const session = await context.get("/api/auth/session", { failOnStatusCode: false });
  if (session.ok()) {
    const body = (await session.json().catch(() => ({}))) as { authenticated?: boolean };
    if (body.authenticated) return context;
  }
  const login = await context.post("/login", {
    form: { password: requireRealPassword() },
    failOnStatusCode: false,
  });
  if (!login.ok()) throw new Error(`sample-context login failed with ${login.status()}`);
  return context;
}
