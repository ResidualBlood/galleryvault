/**
 * Direct online page source: backend resolves, the browser fetches the bytes.
 *
 * Contract: PLAN-frontend-rewrite §3.3 / §3.4.
 *
 * - at most `ONLINE_MAX_RESOLVE_IN_FLIGHT` resolve requests are in flight, so
 *   the reader's two-page preload cannot fan out into extra page-budget usage;
 * - a resolved URL is reused until `expires_at` (minus a small skew) and then
 *   re-resolved before display;
 * - an image that fails to load is re-resolved with `retry=1`, then `retry=2`
 *   (the backend re-fetches the viewer with `nl=` to switch H@H node); after
 *   that the source emits `blocked` so the UI can offer the device proxy or the
 *   official page;
 * - `429 image_limit` (or a 509 placeholder resolved upstream) stops all further
 *   resolution until the reader is reopened or switched to the proxy mode.
 *
 * The image probe loads the resolved URL once with the same browser cache the
 * reader will use, which is the only reliable way to notice a dead H@H node
 * before it is shown as a broken page. It sets `referrerPolicy="no-referrer"`.
 */
import { officialGalleryUrl } from "@/api/eh";
import {
  ONLINE_RESOLVE_MAX_RETRY,
  onlineResolveCode,
  resolveOnlinePage,
  type ResolvedOnlinePage,
} from "@/api/eh-reader";
import type { PageRef, PageSource, PageSourceKind } from "../source";

/** Re-resolve slightly before the backend's 600 s TTL actually elapses. */
export const ONLINE_EXPIRY_SKEW_MS = 5_000;
export const ONLINE_MAX_RESOLVE_IN_FLIGHT = 2;
export const ONLINE_PROBE_TIMEOUT_MS = 20_000;
/**
 * H@H "image limit" placeholders (509.gif / 509s.gif) are tiny; a normal page
 * is never 4×4 or smaller. Anything at or below this edge is treated as a
 * placeholder and retried on another node.
 */
export const ONLINE_PLACEHOLDER_MAX_EDGE = 4;
/** Used only if the backend response omits `expires_at`. */
export const ONLINE_FALLBACK_TTL_MS = 600_000;

export type OnlineSourceErrorCode =
  | "page_out_of_range"
  | "image_limit"
  | "blocked"
  | "upstream"
  | "host_not_allowed"
  | "auth"
  | "challenge"
  | "banned"
  | "unknown";

export class OnlineSourceError extends Error {
  constructor(
    readonly code: OnlineSourceErrorCode,
    message?: string,
  ) {
    super(message ?? code);
    this.name = "OnlineSourceError";
  }
}

export type OnlineSourceEvent =
  | { type: "quota" }
  | { type: "blocked"; page: number; reason: "image_failed" | "placeholder" };

export interface OnlineImageSize {
  width: number;
  height: number;
}

export type OnlineImageProbe = (
  url: string,
  signal?: AbortSignal,
) => Promise<OnlineImageSize>;

export type OnlineResolveFn = (
  page: number,
  retry: number,
  signal?: AbortSignal,
) => Promise<ResolvedOnlinePage>;

export interface OnlineDirectOptions {
  gid: number;
  token: string;
  pageCount: number | null;
  resolve?: OnlineResolveFn;
  probe?: OnlineImageProbe;
  now?: () => number;
  maxResolveInFlight?: number;
}

interface ResolvedEntry {
  index: number;
  url: string;
  width: number;
  height: number;
  /** Epoch ms; null means "no expiry information" (never auto-stale). */
  expiresAt: number | null;
}

/** Load an image once to learn its natural size (and whether it loads at all). */
export function loadImageSize(
  url: string,
  signal?: AbortSignal,
  timeoutMs = ONLINE_PROBE_TIMEOUT_MS,
): Promise<OnlineImageSize> {
  return new Promise((resolve, reject) => {
    if (typeof Image === "undefined") {
      reject(new Error("Image is not available"));
      return;
    }
    const image = new Image();
    image.referrerPolicy = "no-referrer";
    image.decoding = "async";
    let done = false;
    const timer = setTimeout(() => {
      finish(new Error("image probe timed out"));
    }, timeoutMs);
    const onAbort = () => finish(new DOMException("Aborted", "AbortError"));
    function finish(error?: Error): void {
      if (done) return;
      done = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      if (error) {
        image.onload = null;
        image.onerror = null;
        reject(error);
        return;
      }
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    }
    image.onload = () => finish();
    image.onerror = () => finish(new Error("image failed to load"));
    if (signal) {
      if (signal.aborted) {
        finish(new DOMException("Aborted", "AbortError"));
        return;
      }
      signal.addEventListener("abort", onAbort, { once: true });
    }
    image.src = url;
  });
}

/** A 509 placeholder is tiny; real pages never are. */
export function isPlaceholderSize(size: OnlineImageSize): boolean {
  if (!(size.width > 0) || !(size.height > 0)) return false;
  return (
    size.width <= ONLINE_PLACEHOLDER_MAX_EDGE && size.height <= ONLINE_PLACEHOLDER_MAX_EDGE
  );
}

function isRetryableResolveCode(code: string | null): boolean {
  // `page_out_of_range` / auth / challenge / banned / image_limit never improve
  // by switching nodes; upstream / host / network blips can.
  return code === null || code === "upstream" || code === "host_not_allowed";
}

export class OnlineDirectPageSource implements PageSource {
  readonly kind: PageSourceKind = "online-direct";
  readonly pageCount: number | null;

  private readonly gid: number;
  private readonly token: string;
  private readonly resolveFn: OnlineResolveFn;
  private readonly probe: OnlineImageProbe;
  private readonly now: () => number;
  private readonly maxResolveInFlight: number;
  private readonly controller = new AbortController();

  private readonly entries = new Map<number, ResolvedEntry>();
  private readonly inflight = new Map<number, Promise<PageRef>>();
  private readonly blockedPages = new Set<number>();
  private readonly listeners = new Set<(event: OnlineSourceEvent) => void>();

  private activeResolves = 0;
  private readonly waiters: Array<() => void> = [];
  private throttled = false;
  private quotaEventSent = false;
  private disposed = false;

  constructor(options: OnlineDirectOptions) {
    this.gid = options.gid;
    this.token = options.token;
    this.pageCount = options.pageCount;
    this.resolveFn =
      options.resolve ??
      ((page, retry, signal) =>
        resolveOnlinePage(this.gid, this.token, page, retry, { signal }));
    this.probe = options.probe ?? loadImageSize;
    this.now = options.now ?? (() => Date.now());
    this.maxResolveInFlight = Math.max(
      1,
      Math.trunc(options.maxResolveInFlight ?? ONLINE_MAX_RESOLVE_IN_FLIGHT),
    );
  }

  /** True once a 429 image_limit was seen; no further page is resolved. */
  get isThrottled(): boolean {
    return this.throttled;
  }

  get size(): number {
    return this.entries.size;
  }

  subscribe(listener: (event: OnlineSourceEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Cached URL is too close to `expires_at` (or already past it). */
  isExpired(index: number, now = this.now()): boolean {
    const entry = this.entries.get(index);
    if (!entry || entry.expiresAt === null) return false;
    return entry.expiresAt - now <= ONLINE_EXPIRY_SKEW_MS;
  }

  hasPage(index: number): boolean {
    return this.entries.has(index) && !this.isExpired(index);
  }

  /** Resolved dimensions when known (webtoon placeholders). */
  dimensions(index: number): OnlineImageSize | null {
    const entry = this.entries.get(index);
    if (!entry) return null;
    return { width: entry.width, height: entry.height };
  }

  async page(index: number): Promise<PageRef> {
    if (!Number.isInteger(index) || index < 0) {
      throw new RangeError(`invalid page index: ${index}`);
    }
    if (this.pageCount !== null && index >= this.pageCount) {
      throw new RangeError(`page ${index} out of range`);
    }
    if (this.disposed) throw new OnlineSourceError("unknown", "source disposed");

    // Already-resolved pages stay readable after a 429: only *new* resolves stop.
    const cached = this.entries.get(index);
    if (cached && !this.isExpired(index)) return toRef(cached);
    if (this.throttled) throw new OnlineSourceError("image_limit");
    if (this.blockedPages.has(index)) throw new OnlineSourceError("blocked");

    const pending = this.inflight.get(index);
    if (pending) return pending;

    const job = this.resolvePage(index).finally(() => {
      this.inflight.delete(index);
    });
    this.inflight.set(index, job);
    return job;
  }

  officialUrl(): string | null {
    return this.gid > 0 && this.token ? officialGalleryUrl(this.gid, this.token) : null;
  }

  dispose(): void {
    this.disposed = true;
    this.controller.abort();
    this.waiters.splice(0);
    this.inflight.clear();
    this.listeners.clear();
  }

  private async resolvePage(index: number): Promise<PageRef> {
    let retry = 0;
    for (;;) {
      let resolved: ResolvedOnlinePage;
      try {
        resolved = await this.limited(() =>
          this.resolveFn(index + 1, retry, this.controller.signal),
        );
      } catch (error) {
        const code = onlineResolveCode(error);
        if (code === "image_limit") {
          this.markThrottled();
          throw new OnlineSourceError("image_limit");
        }
        if (code && code !== "unknown" && !isRetryableResolveCode(code)) {
          throw new OnlineSourceError(code as OnlineSourceErrorCode);
        }
        if (retry < ONLINE_RESOLVE_MAX_RETRY) {
          retry += 1;
          continue;
        }
        throw new OnlineSourceError(
          (code as OnlineSourceErrorCode | null) ?? "unknown",
        );
      }

      if (!resolved.url) {
        throw new OnlineSourceError("upstream");
      }

      let size: OnlineImageSize;
      try {
        size = await this.probe(resolved.url, this.controller.signal);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") throw error;
        if (retry < ONLINE_RESOLVE_MAX_RETRY) {
          retry += 1;
          continue;
        }
        this.blockedPages.add(index);
        this.emit({ type: "blocked", page: index, reason: "image_failed" });
        throw new OnlineSourceError("blocked");
      }

      if (isPlaceholderSize(size)) {
        if (retry < ONLINE_RESOLVE_MAX_RETRY) {
          retry += 1;
          continue;
        }
        this.blockedPages.add(index);
        this.emit({ type: "blocked", page: index, reason: "placeholder" });
        throw new OnlineSourceError("blocked");
      }

      const fallbackExpiry = this.now() + ONLINE_FALLBACK_TTL_MS;
      const parsed = resolved.expires_at ? Date.parse(resolved.expires_at) : Number.NaN;
      const entry: ResolvedEntry = {
        index,
        url: resolved.url,
        width: size.width || resolved.width,
        height: size.height || resolved.height,
        expiresAt: Number.isFinite(parsed) ? parsed : fallbackExpiry,
      };
      this.entries.set(index, entry);
      return toRef(entry);
    }
  }

  private markThrottled(): void {
    this.throttled = true;
    if (this.quotaEventSent) return;
    this.quotaEventSent = true;
    this.emit({ type: "quota" });
  }

  private emit(event: OnlineSourceEvent): void {
    for (const listener of [...this.listeners]) listener(event);
  }

  private async limited<T>(task: () => Promise<T>): Promise<T> {
    if (this.activeResolves >= this.maxResolveInFlight) {
      await new Promise<void>((resolve) => this.waiters.push(resolve));
    }
    this.activeResolves += 1;
    try {
      return await task();
    } finally {
      this.activeResolves -= 1;
      this.waiters.shift()?.();
    }
  }
}

function toRef(entry: ResolvedEntry): PageRef {
  return {
    index: entry.index,
    url: entry.url,
    meta: { width: entry.width, height: entry.height },
  };
}
