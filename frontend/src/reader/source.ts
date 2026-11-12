/**
 * Page source abstraction shared by the local reader and both online modes.
 *
 * - local: pages are served by the GalleryVault backend
 *   (`/api/galleries/{id}/pages/{n}`).
 * - online-direct: the page resolver returns EH image URLs that the browser
 *   fetches directly, so no EH request budget is spent on the server.
 * - online-proxy: optional per-device fallback through the backend image proxy.
 */
export type PageSourceKind = "local" | "online-direct" | "online-proxy";

export interface PageRef {
  /** Zero-based page index. */
  index: number;
  /** Playable image URL for this page. */
  url: string;
  /** Optional per-page metadata (animated image duration, dimensions). */
  meta?: Record<string, unknown>;
}

/** Reading-progress payload shared by the local and online writers. */
export interface PageProgress {
  /** Zero-based page index. */
  current_page: number;
  total_pages: number;
}

export interface PageSource {
  readonly kind: PageSourceKind;
  /** Total number of pages, or null while unknown. */
  readonly pageCount: number | null;
  /** Resolve a page. Implementations may refresh expired online tokens. */
  page(index: number): Promise<PageRef>;
  /** Absolute URL of the original official page, when available. */
  officialUrl(): string | null;
  /**
   * Optional progress writer owned by the source.
   *
   * `LocalPageSource` writes `/api/galleries/{id}/progress`. Online sources do
   * not implement it: the online view passes `progressSender` to ReaderShell so
   * an EH gid that collides with a local `gallery_id` can never write local
   * progress.
   */
  saveProgress?(progress: PageProgress): Promise<unknown>;
}

export function isOnline(source: PageSource): boolean {
  return source.kind !== "local";
}
