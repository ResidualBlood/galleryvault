import type { Page } from "@playwright/test";
import { onlineGalleryPath } from "../../../src/api/eh-reader";
import {
  READER_GID,
  READER_PAGES,
  READER_TOKEN,
  detailResponse,
  historyResponse,
  pageSvg,
  progressPayload,
} from "./data";

/**
 * Mock backend + H@H for the online reader E2E suite.
 *
 * Nothing reaches the network: `/api/eh/*` is answered locally, every H@H
 * image host is intercepted, and any other external request is aborted (and
 * recorded) so a misconfigured URL fails the test instead of touching the real
 * ExHentai / H@H infrastructure.
 */
export type ReaderScenario = "basic" | "retry" | "blocked" | "quota" | "expiry";

export interface ReaderMockOptions {
  scenario?: ReaderScenario;
  /** Stored progress returned by GET (null → 404, like a never-read gallery). */
  progress?: { page: number; total_pages: number } | null;
  historyCount?: number;
}

export interface ReaderMockMetrics {
  resolves: Array<{ page: number; retry: number }>;
  images: Array<{ url: string; referer: string | null; cookie: string | null }>;
  proxyImages: string[];
  maxInflightResolves: number;
  /** Resolve attempts observed after the 429 response (must stay 0). */
  resolvesAfterQuota: number;
  quotaRequests: number;
  progressSaves: Array<{
    page: number;
    total_pages?: number;
    title?: string;
    thumb?: string;
  }>;
  blockedExternal: string[];
}

const IMAGE_HOST = /^https:\/\/[a-z0-9]+\.hath\.network:8443\//i;
const GALLERY = onlineGalleryPath(READER_GID, READER_TOKEN);
const escapeRe = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const DEAD_IMAGE = /\/h\/\d+-\d+-dead\.jpg/;

function isDead(scenario: ReaderScenario, page: number, retry: number): boolean {
  // 1-based server page numbers.
  if (scenario === "retry") return page === 2 && retry === 0;
  if (scenario === "blocked") return page === 3;
  return false;
}

function imageUrl(page: number, retry: number, dead: boolean): string {
  return `https://n${retry}.hath.network:8443/h/${page}-${retry}-${dead ? "dead" : "ok"}.jpg?keystamp=fixture`;
}

export async function mockOnlineReaderBackend(
  page: Page,
  options: ReaderMockOptions = {},
): Promise<ReaderMockMetrics> {
  const scenario = options.scenario ?? "basic";
  const metrics: ReaderMockMetrics = {
    resolves: [],
    images: [],
    proxyImages: [],
    maxInflightResolves: 0,
    resolvesAfterQuota: 0,
    quotaRequests: 0,
    progressSaves: [],
    blockedExternal: [],
  };

  let saved = options.progress ?? null;
  let inflight = 0;
  let quotaHit = false;

  // Registered first so every later, more specific route wins (Playwright
  // matches routes in reverse registration order).
  await page.route(/^https?:\/\/(?!127\.0\.0\.1(?:[:/]|$))/, async (route) => {
    metrics.blockedExternal.push(route.request().url());
    await route.abort();
  });

  await page.route("**/api/eh/history*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(historyResponse(options.historyCount ?? 3)),
    });
  });

  await page.route("**/api/quota", async (route) => {
    metrics.quotaRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        gp: 1234,
        image_limit: { current: 5000, limit: 5000 },
        checked_at: "2026-11-12T10:00:00Z",
        error: null,
      }),
    });
  });

  // Local reader progress: the shell always owns one writer keyed by
  // galleryId. It is out of this batch's scope; answer quickly so retries do
  // not stall the reader.
  await page.route("**/api/galleries/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "local gallery not found" }),
    });
  });

  await page.route(
    new RegExp(`${escapeRe(GALLERY)}/progress$`),
    async (route) => {
      const method = route.request().method();
      if (method === "PUT") {
        const body = JSON.parse(route.request().postData() ?? "{}") as {
          page?: number;
          total_pages?: number;
          title?: string;
          thumb?: string;
        };
        metrics.progressSaves.push(body as ReaderMockMetrics["progressSaves"][number]);
        const payload = {
          page: body.page ?? 1,
          total_pages: body.total_pages ?? READER_PAGES,
          title: body.title,
          thumb: body.thumb,
        };
        saved = { page: payload.page, total_pages: payload.total_pages };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(progressPayload(payload.page, payload.total_pages)),
        });
        return;
      }
      if (!saved) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "No online reading progress" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(progressPayload(saved.page, saved.total_pages)),
      });
    },
  );

  await page.route(
    new RegExp(`${escapeRe(GALLERY)}/pages/(\\d+)/image$`),
    async (route) => {
      metrics.proxyImages.push(route.request().url());
      const match = new URL(route.request().url()).pathname.match(/\/pages\/(\d+)\/image$/);
      await route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: pageSvg(Number(match?.[1] ?? 1) - 1),
      });
    },
  );

  await page.route(
    new RegExp(`${escapeRe(GALLERY)}/pages/(\\d+)/resolve`),
    async (route) => {
      const url = new URL(route.request().url());
      const match = url.pathname.match(/\/pages\/(\d+)\/resolve$/);
      const target = Number(match?.[1] ?? 1);
      const retry = Number(url.searchParams.get("retry") ?? "0") || 0;
      if (quotaHit) {
        metrics.resolvesAfterQuota += 1;
      }
      metrics.resolves.push({ page: target, retry });
      inflight += 1;
      metrics.maxInflightResolves = Math.max(metrics.maxInflightResolves, inflight);
      await new Promise((done) => setTimeout(done, 120));
      inflight -= 1;

      if (scenario === "quota" && target >= 8 && !quotaHit) {
        quotaHit = true;
        await route.fulfill({
          status: 429,
          contentType: "application/json",
          body: JSON.stringify({ detail: { code: "image_limit" } }),
        });
        return;
      }
      if (quotaHit) {
        await route.fulfill({
          status: 429,
          contentType: "application/json",
          body: JSON.stringify({ detail: { code: "image_limit" } }),
        });
        return;
      }

      const dead = isDead(scenario, target, retry);
      const ttl = scenario === "expiry" && target === 1 ? 1_500 : 600_000;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          state: "ok",
          page: target,
          url: imageUrl(target, retry, dead),
          width: 800,
          height: 1200,
          expires_at: new Date(Date.now() + ttl).toISOString(),
        }),
      });
    },
  );

  await page.route(
    new RegExp(`${escapeRe(GALLERY)}$`),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(detailResponse()),
      });
    },
  );

  await page.route(IMAGE_HOST, async (route) => {
    const request = route.request();
    const headers = request.headers();
    metrics.images.push({
      url: request.url(),
      referer: headers.referer ?? headers.referrer ?? null,
      cookie: headers.cookie ?? null,
    });
    if (DEAD_IMAGE.test(request.url())) {
      await route.fulfill({ status: 500, contentType: "text/plain", body: "dead node" });
      return;
    }
    const match = request.url().match(/\/h\/(\d+)-/);
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: pageSvg(Number(match?.[1] ?? 1) - 1),
    });
  });

  await page.route("https://ehgt.org/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/svg+xml", body: pageSvg(0, 400, 600) });
  });

  return metrics;
}
