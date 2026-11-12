import { request, type Endpoint, type RequestOptions } from "./client";
import { galleryEp, galleryProgressEp } from "./galleries";

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

function withId(endpoint: Endpoint<"GET">, id: number): Endpoint<"GET"> {
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
