/**
 * Single HTTP entry point for the GalleryVault frontend.
 *
 * Contract (matches the existing backend, see inv-frontend.md §1):
 *   - every request carries cookies (`credentials: "include"`);
 *   - write methods carry `X-CSRF-Token` copied from the `galleryvault_csrf`
 *     cookie (double-submit, cookie is intentionally not httpOnly);
 *   - a 401 clears the auth store through the registered handler, except for
 *     the session probe and login itself;
 *   - every request has a default timeout and accepts a caller AbortSignal.
 *
 * Endpoints are declared in `src/api/<domain>.ts` with `ep()`; ESLint rejects
 * bare `/api/` strings outside this directory.
 */

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface Endpoint<M extends HttpMethod = HttpMethod> {
  readonly method: M;
  readonly path: string;
}

export const ep = <M extends HttpMethod, P extends string>(
  method: M,
  path: P,
): Endpoint<M> => ({ method, path });

const WRITE_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const CSRF_COOKIE = "galleryvault_csrf";
const DEFAULT_TIMEOUT_MS = 30_000;

export interface RequestOptions {
  /** JSON body; ignored for GET/HEAD. */
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Do not run the global 401 handler (session probe / login). */
  skipAuthRedirect?: boolean;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly code: "http" | "timeout" | "network";

  constructor(
    message: string,
    options: { status?: number; detail?: unknown; code?: ApiError["code"] } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? 0;
    this.detail = options.detail;
    this.code = options.code ?? "http";
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registered once from main.ts after Pinia and the router are installed. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

export function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${CSRF_COOKIE}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : "";
}

function buildHeaders(method: HttpMethod, body: unknown, contentType?: string): Headers {
  const headers = new Headers();
  if (WRITE_METHODS.has(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  if (body !== undefined && contentType) {
    headers.set("Content-Type", contentType);
  }
  return headers;
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  if (detail !== undefined && detail !== null) {
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return null;
  }
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function execute(
  endpoint: Endpoint,
  options: RequestOptions,
  contentType?: string,
): Promise<unknown> {
  const { method, path } = endpoint;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  let timedOut = false;
  const timer =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : null;

  const external = options.signal;
  const onExternalAbort = () => controller.abort(external?.reason);
  if (external) {
    if (external.aborted) controller.abort(external.reason);
    else external.addEventListener("abort", onExternalAbort, { once: true });
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "include",
      headers: buildHeaders(method, options.body, contentType),
      body:
        options.body === undefined
          ? undefined
          : contentType === "application/json"
            ? JSON.stringify(options.body)
            : (options.body as BodyInit),
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) {
      throw new ApiError(`Request timed out after ${timeoutMs}ms`, {
        code: "timeout",
      });
    }
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    if (external?.aborted) throw error;
    throw new ApiError(
      error instanceof Error ? error.message : "Network request failed",
      { code: "network" },
    );
  } finally {
    if (timer !== null) clearTimeout(timer);
    external?.removeEventListener("abort", onExternalAbort);
  }

  if (response.status === 401 && !options.skipAuthRedirect) {
    unauthorizedHandler?.();
  }

  const data = await parseBody(response);
  if (!response.ok) {
    const raw =
      data && typeof data === "object"
        ? (data as { detail?: unknown; message?: unknown })
        : null;
    const detail = raw?.detail ?? raw?.message ?? data ?? response.statusText;
    throw new ApiError(detailMessage(detail, response.statusText || "Request failed"), {
      status: response.status,
      detail,
    });
  }
  return data;
}

export function request<T = unknown>(
  endpoint: Endpoint,
  options: RequestOptions = {},
): Promise<T> {
  return execute(endpoint, options, "application/json") as Promise<T>;
}

/** Login/logout are form-encoded and intentionally outside `/api/`. */
export function requestForm<T = unknown>(
  endpoint: Endpoint,
  fields: Record<string, string>,
  options: RequestOptions = {},
): Promise<T> {
  const body = new URLSearchParams(fields).toString();
  return execute(endpoint, { ...options, body }, "application/x-www-form-urlencoded") as Promise<T>;
}

export const REQUEST_DEFAULT_TIMEOUT_MS = DEFAULT_TIMEOUT_MS;
