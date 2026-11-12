import { ep, request, type RequestOptions } from "./client";

/**
 * Local reader endpoints. Online reader endpoints live in `online.ts` and are
 * wired in Batch 5; this module only covers the local page source.
 */

export interface ReaderGalleryPage {
  index?: number;
  page_index?: number;
  name?: string;
  member_name?: string;
  media_type?: string;
}

export interface ReaderGallery {
  id: number;
  gid?: number | null;
  token?: string | null;
  title?: string | null;
  title_english?: string | null;
  title_jpn?: string | null;
  page_count?: number | null;
  file_size?: number | null;
  favorite?: boolean | null;
  reading_progress?: number | null;
  pages?: ReaderGalleryPage[];
}

export interface ReaderProgress {
  current_page?: number | null;
  total_pages?: number | null;
}

export interface ReaderPageMeta {
  animated: boolean;
  /** Total animation duration in milliseconds, capped by the backend at 120000. */
  duration_ms: number;
}

export const readerGalleryEp = ep("GET", "/api/galleries/{id}");
export const readerProgressEp = ep("GET", "/api/galleries/{id}/progress");
export const readerSaveProgressEp = ep("PUT", "/api/galleries/{id}/progress");
export const readerNextGalleryEp = ep("GET", "/api/galleries/{id}/next");
export const readerPageMetaEp = ep("GET", "/api/galleries/{id}/pages/{id}/meta");

function fill(path: string, params: Record<string, string | number>): string {
  return path.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in params ? encodeURIComponent(String(params[key])) : match,
  );
}

/** Image URL for one page of a local gallery. */
export function readerPagePath(galleryId: number | string, index: number): string {
  return `/api/galleries/${encodeURIComponent(String(galleryId))}/pages/${index}`;
}

export function getReaderGallery(
  galleryId: number | string,
  options: RequestOptions = {},
): Promise<ReaderGallery> {
  return request<ReaderGallery>(
    { ...readerGalleryEp, path: fill(readerGalleryEp.path, { id: galleryId }) },
    options,
  );
}

export function getReaderProgress(
  galleryId: number | string,
  options: RequestOptions = {},
): Promise<ReaderProgress> {
  return request<ReaderProgress>(
    { ...readerProgressEp, path: fill(readerProgressEp.path, { id: galleryId }) },
    options,
  );
}

export function saveReaderProgress(
  galleryId: number | string,
  payload: { current_page: number; total_pages: number },
  options: RequestOptions = {},
): Promise<unknown> {
  return request<unknown>(
    {
      ...readerSaveProgressEp,
      path: fill(readerSaveProgressEp.path, { id: galleryId }),
    },
    { ...options, body: payload },
  );
}

export function getNextGallery(
  galleryId: number | string,
  options: RequestOptions = {},
): Promise<{ id: number }> {
  return request<{ id: number }>(
    { ...readerNextGalleryEp, path: fill(readerNextGalleryEp.path, { id: galleryId }) },
    options,
  );
}

/**
 * Probe one local page for animation timing (GIF/WebP).
 *
 * `readerPageMetaEp.path` has two `{id}` placeholders; `fill` replaces every
 * occurrence at once, so substitute gallery and page index one at a time.
 */
export async function getReaderPageMeta(
  galleryId: number | string,
  pageIndex: number,
  options: RequestOptions = {},
): Promise<ReaderPageMeta> {
  if (!Number.isInteger(pageIndex) || pageIndex < 0) {
    throw new RangeError(`invalid page index: ${pageIndex}`);
  }
  const path = readerPageMetaEp.path
    .replace("{id}", encodeURIComponent(String(galleryId)))
    .replace("{id}", encodeURIComponent(String(pageIndex)));
  const data = await request<Partial<ReaderPageMeta>>(
    { method: readerPageMetaEp.method, path },
    options,
  );
  const duration = Number(data?.duration_ms);
  return {
    animated: Boolean(data?.animated),
    duration_ms: Number.isFinite(duration)
      ? Math.max(0, Math.min(120_000, duration))
      : 0,
  };
}
