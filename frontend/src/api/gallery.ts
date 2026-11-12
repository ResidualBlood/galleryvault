import { request, type Endpoint, type HttpMethod, type RequestOptions } from "./client";
import {
  deleteGalleryEp,
  downloadGalleryOriginalEp,
  exportGalleryCbzEp,
  galleryEp,
  galleryFavoriteEp,
  galleryProgressEp,
  galleryThumbEp,
  patchGalleryLocalEp,
  redownloadGalleryEp,
} from "./galleries";
import { favoriteNoteEp } from "./favorites";

export interface GalleryTag {
  namespace: string;
  name: string;
  display?: string | null;
}

export interface GalleryPage {
  index: number;
  page_index?: number;
  name?: string | null;
  member_name?: string | null;
  media_type?: string | null;
  image_url?: string | null;
  thumb_url?: string | null;
}

export interface GalleryDetail {
  id: number;
  gid?: number | null;
  token?: string | null;
  title: string;
  title_english?: string | null;
  title_jpn?: string | null;
  storage_type?: string | null;
  category?: string | null;
  page_count: number;
  file_size?: number | null;
  storage_size?: number | null;
  uploader?: string | null;
  posted_at?: string | null;
  rating?: number | null;
  favorite?: boolean;
  favorite_category?: number | null;
  reading_progress?: number | null;
  expunged?: boolean;
  image_quality?: string | null;
  local_rating?: number | null;
  local_note?: string | null;
  storage_path?: string | null;
  eh_url?: string | null;
  exhentai_url?: string | null;
  tags?: GalleryTag[];
  pages?: GalleryPage[];
}

export interface GalleryProgress {
  gallery_id: number;
  current_page: number;
  total_pages: number;
  updated_at?: string | null;
}

export type GalleryRequestOptions = Omit<RequestOptions, "signal"> & {
  signal?: AbortSignal;
};

function withId<M extends HttpMethod>(endpoint: Endpoint<M>, id: number): Endpoint<M> {
  return {
    method: endpoint.method,
    path: endpoint.path.replace("{id}", String(id)),
  };
}

/** Thumbnail URL for page `index`; keep this in the API layer so views never
 * hand-build `/api/...` strings (ESLint bare-path guard). */
export function galleryThumbUrl(galleryId: number, index: number): string {
  return `/api/galleries/${galleryId}/thumb/${index}`;
}

export function getGallery(
  id: number,
  options: GalleryRequestOptions = {},
): Promise<GalleryDetail> {
  return request<GalleryDetail>(withId(galleryEp, id), options);
}

export function getGalleryProgress(
  id: number,
  options: GalleryRequestOptions = {},
): Promise<GalleryProgress> {
  return request<GalleryProgress>(withId(galleryProgressEp, id), options);
}

/* --------------------------------------------------------- manage actions */

export interface GalleryFavoriteInfo {
  gid: number | null;
  token: string | null;
  favorite: boolean;
  favcats: number[];
  favcat_names: Array<{ favcat: number; name: string }>;
  note: string | null;
}

export interface GalleryLocalInput {
  local_rating?: number | null;
  local_note?: string | null;
  local_tags?: string[];
}

export interface GalleryLocalResult {
  id?: number;
  local_rating?: number | null;
  local_note?: string | null;
  tags?: GalleryTag[];
}

/** Page thumbnail URL (kept out of views so they never build `/api/` paths). */
export function galleryThumbPath(galleryId: number, index: number): string {
  return galleryThumbEp.path
    .replace("{id}", String(galleryId))
    .replace("{id}", String(index));
}

export function getGalleryFavorite(
  id: number,
  options: GalleryRequestOptions = {},
): Promise<GalleryFavoriteInfo> {
  return request<GalleryFavoriteInfo>(withId(galleryFavoriteEp, id), options);
}

export function patchGalleryLocal(
  id: number,
  input: GalleryLocalInput,
  options: GalleryRequestOptions = {},
): Promise<GalleryLocalResult> {
  return request<GalleryLocalResult>(withId(patchGalleryLocalEp, id), {
    ...options,
    body: input,
  });
}

export function deleteGallery(
  id: number,
  deleteFiles: boolean,
  options: GalleryRequestOptions = {},
): Promise<{ deleted?: boolean }> {
  const endpoint = withId(deleteGalleryEp, id);
  const separator = endpoint.path.includes("?") ? "&" : "?";
  return request<{ deleted?: boolean }>(
    { method: endpoint.method, path: `${endpoint.path}${separator}delete_files=${deleteFiles ? "true" : "false"}` },
    options,
  );
}

export function redownloadGallery(
  id: number,
  options: GalleryRequestOptions = {},
): Promise<{ status?: string; queued?: boolean }> {
  return request<{ status?: string; queued?: boolean }>(withId(redownloadGalleryEp, id), options);
}

export function downloadGalleryOriginal(
  id: number,
  archive: boolean,
  options: GalleryRequestOptions = {},
): Promise<{ status?: string; queued?: boolean }> {
  return request<{ status?: string; queued?: boolean }>(withId(downloadGalleryOriginalEp, id), {
    ...options,
    body: { archive },
  });
}

export interface FavoriteNoteInput {
  gid: number;
  token?: string | null;
  favcat?: number | null;
  note: string;
}

/** Cloud-first favourite note; only `cloud_ok` updates the local copy. */
export function setGalleryFavoriteNote(
  input: FavoriteNoteInput,
  options: GalleryRequestOptions = {},
): Promise<{ gid: number; cloud_ok: boolean; local_updated?: number; note?: string | null }> {
  return request<{ gid: number; cloud_ok: boolean; local_updated?: number; note?: string | null }>(favoriteNoteEp, {
    ...options,
    body: {
      gid: input.gid,
      token: input.token ?? "",
      favcat: input.favcat ?? 0,
      note: input.note,
    },
  });
}

/** Direct download link for the CBZ export (rendered as an `<a download>`). */
export function galleryExportCbzUrl(id: number): string {
  return exportGalleryCbzEp.path.replace("{id}", String(id));
}
