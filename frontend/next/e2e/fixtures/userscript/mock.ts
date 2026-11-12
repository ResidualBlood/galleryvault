/**
 * Minimal GalleryVault backend for the companion userscript E2E.
 *
 * The userscript talks to a user-configured origin through GM_xmlhttpRequest.
 * The Playwright shim forwards those calls from Node (like the extension does),
 * so this server is the only network peer besides the EH fixture page.
 */

/* eslint-disable no-restricted-syntax -- standalone userscript E2E asserts raw API paths outside the SPA client */

import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export const MOCK_GID = 1526342;
export const MOCK_EH_TOKEN = "0123abcd45";
export const MOCK_API_TOKEN = "tok-e2e-companion-8c1f2a";

export interface RecordedRequest {
  method: string;
  path: string;
  headers: Record<string, string | string[] | undefined>;
  body: string;
}

export interface StatusItem {
  gid: number;
  in_library: boolean;
  gallery_id: number | null;
  favorited: boolean;
  favcat: number | null;
  download_status: string | null;
}

export interface MockOptions {
  /** Every `/api/**` call answers 401, like a revoked token. */
  unauthorized?: boolean;
  status?: StatusItem;
}

export interface MockBackend {
  baseUrl: string;
  requests: RecordedRequest[];
  /** Requests that reached an unexpected path. */
  notFound: string[];
  close: () => Promise<void>;
}

const DEFAULT_STATUS: StatusItem = {
  gid: MOCK_GID,
  in_library: true,
  gallery_id: 42,
  favorited: true,
  favcat: 2,
  download_status: "downloading",
};

function sendJson(response: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}

function readBody(request: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    request.on("error", () => resolve(""));
  });
}

export async function startMockBackend(options: MockOptions = {}): Promise<MockBackend> {
  const requests: RecordedRequest[] = [];
  const notFound: string[] = [];
  const status = options.status ?? DEFAULT_STATUS;

  const server: Server = createServer(async (request, response) => {
    const url = new URL(request.url || "/", "http://127.0.0.1");
    const body = await readBody(request);
    requests.push({
      method: request.method || "GET",
      path: `${url.pathname}${url.search}`,
      headers: request.headers,
      body,
    });

    if (options.unauthorized) {
      sendJson(response, 401, { detail: "unauthorized" });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/eh/status") {
      const gids = (url.searchParams.get("gids") || "")
        .split(",")
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
      const items = gids.map((gid) => ({ ...status, gid }));
      sendJson(response, 200, { items });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/favorites/categories") {
      sendJson(response, 200, [
        { favcat: 0, name: "Favorites" },
        { favcat: 2, name: "Doujinshi" },
        { favcat: 3, name: "Manga" },
      ]);
      return;
    }

    if (request.method === "POST" && url.pathname === "/api/downloads") {
      let payload: { gid?: number; title?: string } = {};
      try {
        payload = JSON.parse(body || "{}");
      } catch {
        payload = {};
      }
      sendJson(response, 200, {
        id: 77,
        gid: payload.gid ?? MOCK_GID,
        title: payload.title ?? "Sample Gallery Title (sanitized fixture)",
        status: "pending",
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/api/favorites/add") {
      let payload: { gid?: number; target_favcat?: number } = {};
      try {
        payload = JSON.parse(body || "{}");
      } catch {
        payload = {};
      }
      const gid = payload.gid ?? MOCK_GID;
      sendJson(response, 200, {
        gids: [gid],
        target_favcat: payload.target_favcat ?? 0,
        cloud_ok: true,
        cloud_failed: [],
        successful_gids: [gid],
        cloud_added: 1,
        local_added: 1,
      });
      return;
    }

    notFound.push(`${request.method} ${url.pathname}`);
    sendJson(response, 404, { detail: "not_found" });
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    requests,
    notFound,
    close: () =>
      new Promise<void>((resolve) => {
        server.close(() => resolve());
      }),
  };
}

/** Requests recorded on the panel's API surface. */
export function apiRequests(backend: MockBackend, path: string): RecordedRequest[] {
  return backend.requests.filter((request) => request.path.split("?")[0] === path);
}

export function authorizationOf(request: RecordedRequest | undefined): string {
  const header = request?.headers.authorization;
  return typeof header === "string" ? header : "";
}
