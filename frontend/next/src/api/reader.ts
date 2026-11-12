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
