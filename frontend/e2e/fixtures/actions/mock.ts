import type { Page, Route } from "@playwright/test";
import {
  addFavoritesEp,
  favoriteCategoriesEp,
  moveFavoritesEp,
  removeFavoritesEp,
} from "@/api/favorites";
import { createDownloadEp, downloadsEp } from "@/api/downloads";
import { ehStatusEp } from "@/api/eh";

export type MockStatusPhase = "none" | "pending" | "downloading" | "success" | "failed";

export interface ActionsMockOptions {
  /** HTTP status for POST /api/favorites/add (default 200). */
  addStatus?: number;
  /** Return 200 with cloud_failed / successful_gids empty. */
  addCloudFail?: boolean;
  /** Per-call /api/eh/status phases; the last entry repeats. */
  statusSequence?: MockStatusPhase[];
  progress?: { current: number; total: number };
  /**
   * Hand unmatched `/api/**` calls to the next (earlier registered) handler
   * instead of answering `{}`. Required when composing with another backend
   * mock (online list / reader / gallery fixtures).
   */
  fallbackUnknown?: boolean;
}

export interface RecordedWrite {
  path: string;
  method: string;
  csrf: string;
  body: Record<string, unknown>;
}

export interface ActionsMock {
  writes: RecordedWrite[];
  statusCalls: number;
  addRequests: number;
  statusPhases: MockStatusPhase[];
}

const DEFAULT_STATUS: MockStatusPhase[] = ["none", "pending", "downloading", "downloading", "success"];

function json(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function statusItem(gid: number, phase: MockStatusPhase) {
  return {
    gid,
    in_library: phase === "success",
    gallery_id: phase === "success" ? gid + 1000 : null,
    favorited: false,
    favcat: null,
    download_status:
      phase === "none"
        ? null
        : phase === "success"
          ? "success"
          : phase === "failed"
            ? "failed"
            : phase,
  };
}

/**
 * Mock the favorites / downloads / eh status endpoints used by the quick
 * actions. Every write is recorded so the spec can assert CSRF and bodies.
 */
export async function mockActionsBackend(
  page: Page,
  options: ActionsMockOptions = {},
): Promise<ActionsMock> {
  const state: ActionsMock = {
    writes: [],
    statusCalls: 0,
    addRequests: 0,
    statusPhases: [],
  };
  const sequence = options.statusSequence?.length ? options.statusSequence : DEFAULT_STATUS;
  const gids = new Set<number>();

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    // `**/api/**` also matches Vite module URLs such as `/src/api/eh.ts`.
    if (!url.pathname.startsWith("/api")) {
      await route.fallback();
      return;
    }

    if (method !== "GET" && method !== "HEAD") {
      let body: Record<string, unknown> = {};
      try {
        body = (request.postDataJSON() ?? {}) as Record<string, unknown>;
      } catch {
        body = {};
      }
      state.writes.push({
        path: url.pathname,
        method,
        csrf: request.headers()["x-csrf-token"] ?? "",
        body,
      });
    }

    if (url.pathname === favoriteCategoriesEp.path) {
      await json(
        route,
        200,
        Array.from({ length: 10 }, (_, favcat) => ({
          favcat,
          name: `Folder ${favcat}`,
          cloud_count: favcat * 2,
        })),
      );
      return;
    }

    if (url.pathname === addFavoritesEp.path) {
      state.addRequests += 1;
      const body = (request.postDataJSON() ?? {}) as { gid?: number; target_favcat?: number };
      if (options.addStatus && options.addStatus >= 400) {
        await json(route, options.addStatus, { detail: "cloud unavailable" });
        return;
      }
      const gid = Number(body.gid) || 0;
      if (options.addCloudFail) {
        await json(route, 200, {
          gids: [gid],
          target_favcat: body.target_favcat ?? 0,
          cloud_ok: false,
          cloud_added: 0,
          cloud_failed: [gid],
          successful_gids: [],
          local_added: 0,
        });
        return;
      }
      await json(route, 200, {
        gids: [gid],
        target_favcat: body.target_favcat ?? 0,
        cloud_ok: true,
        cloud_added: 1,
        cloud_failed: [],
        successful_gids: [gid],
        local_added: 1,
      });
      return;
    }

    if (url.pathname === moveFavoritesEp.path || url.pathname === removeFavoritesEp.path) {
      const body = (request.postDataJSON() ?? {}) as { gids?: number[] };
      await json(route, 200, {
        gids: body.gids ?? [],
        cloud_ok: true,
        cloud_failed: [],
        successful_gids: body.gids ?? [],
      });
      return;
    }

    if (url.pathname === ehStatusEp.path) {
      const raw = url.searchParams.get("gids") ?? "";
      for (const part of raw.split(",")) {
        const gid = Number(part);
        if (Number.isInteger(gid) && gid > 0) gids.add(gid);
      }
      const index = Math.min(state.statusCalls, sequence.length - 1);
      const phase = sequence[index];
      state.statusCalls += 1;
      state.statusPhases.push(phase);
      await json(route, 200, {
        items: [...gids].map((gid) => statusItem(gid, phase)),
      });
      return;
    }

    if (url.pathname === downloadsEp.path && method === "GET") {
      const status = url.searchParams.get("status");
      const progress = options.progress ?? { current: 3, total: 10 };
      const items =
        status === "downloading"
          ? [...gids].map((gid) => ({
              id: 9,
              gid,
              title: "Harness Gallery",
              status: "downloading",
              current_page: progress.current,
              total_pages: progress.total,
            }))
          : [];
      await json(route, 200, { total: items.length, page: 1, page_size: 500, items });
      return;
    }

    if (url.pathname === createDownloadEp.path && method === "POST") {
      const body = (request.postDataJSON() ?? {}) as { gid?: number };
      await json(route, 202, {
        id: 9,
        gid: Number(body.gid) || 0,
        title: "Harness Gallery",
        status: "pending",
      });
      return;
    }

    if (options.fallbackUnknown) {
      await route.fallback();
      return;
    }
    await json(route, 200, {});
  });

  return state;
}
