import { ep, request } from "./client";

/* ------------------------------------------------------------------ lists */

export const listsEp = ep("GET", "/api/lists");
export const createListEp = ep("POST", "/api/lists");
export const listItemsEp = ep("POST", "/api/lists/{id}/items");
export const removeListItemsEp = ep("POST", "/api/lists/{id}/items/remove");

/* --------------------------------------------------------- saved searches */

export const savedSearchesEp = ep("GET", "/api/saved-searches");
export const createSavedSearchEp = ep("POST", "/api/saved-searches");
export const deleteSavedSearchEp = ep("DELETE", "/api/saved-searches/{id}");

/* ----------------------------------------------------------------- series */

export const seriesEp = ep("GET", "/api/series");
export const createSeriesEp = ep("POST", "/api/series");
export const rebuildSeriesEp = ep("POST", "/api/series/rebuild");
export const patchSeriesEp = ep("PATCH", "/api/series/{id}");
export const deleteSeriesEp = ep("DELETE", "/api/series/{id}");
export const seriesCloudCandidatesEp = ep(
  "GET",
  "/api/series/{id}/cloud-candidates",
);
export const addSeriesCloudItemsEp = ep(
  "POST",
  "/api/series/{id}/cloud-items",
);
export const removeSeriesCloudItemsEp = ep(
  "POST",
  "/api/series/{id}/cloud-items/remove",
);
export const removeSeriesItemsEp = ep(
  "POST",
  "/api/series/{id}/items/remove",
);

/* ------------------------------------------------------------------- tags */

export const tagsSearchEp = ep("GET", "/api/tags/search");
export const reloadTagsEp = ep("POST", "/api/tags/search/reload");
export const tagsStatusEp = ep("GET", "/api/tags/search/status");
export const startTagSyncEp = ep("POST", "/api/tag-sync/start");
export const repairTagCategoriesEp = ep(
  "POST",
  "/api/tag-sync/repair-categories",
);

/* ---------------------------------------------------------------- history */

export const historyEp = ep("GET", "/api/history");
export const clearHistoryEp = ep("DELETE", "/api/history");

/* ------------------------------------------------------------- browse data */

/**
 * State owned by `GalleryListStore` and shared by the browse/library views.
 *
 * The backend contract lives in backend/galleryvault/app/routers/galleries.py
 * (`GET /api/galleries`), tags.py (`GET /api/tags/search`) and
 * galleries.py#history. Do not invent fields: the card only renders what the
 * list endpoint returns.
 */
export interface GalleryTag {
  namespace: string | null;
  name: string;
  display?: string | null;
}

export interface GalleryItem {
  id: number;
  gid: number | null;
  token: string | null;
  title: string;
  title_english?: string | null;
  title_jpn?: string | null;
  storage_type?: string | null;
  category: string;
  page_count: number;
  cover_url: string | null;
  tags: GalleryTag[];
  uploader?: string | null;
  posted_at?: string | null;
  file_size?: number | null;
  storage_size?: number | null;
  rating?: number | null;
  favorite?: boolean;
  favorite_category?: number | null;
  reading_progress?: number | null;
  expunged?: boolean;
  image_quality?: string | null;
  local_rating?: number | null;
  local_note?: string | null;
}

export interface GalleryPage {
  total: number;
  page: number;
  page_size: number;
  q?: string;
  tags?: string;
  resolved?: boolean;
  tag_mode?: string;
  tag_match?: string;
  order_by?: string;
  read_status?: string;
  category?: string;
  items: GalleryItem[];
}

export interface GalleryQuery {
  page?: number;
  page_size?: number;
  q?: string;
  category?: string;
  tags?: string;
  tag_mode?: "and" | "or";
  tag_match?: "exact" | "fuzzy";
  order_by?: string;
  read_status?: string;
  min_rating?: number;
  page_min?: number;
  page_max?: number;
  size_min?: number;
  size_max?: number;
  posted_from?: string;
  posted_to?: string;
  uploader?: string;
  image_quality?: string;
  min_local_rating?: number;
  list_id?: number;
}

export interface HistoryItem {
  gallery_id: number;
  current_page: number;
  total_pages: number;
  last_read_at: string | null;
  title: string | null;
  display_title: string | null;
  raw_title?: string | null;
  title_jpn?: string | null;
  gid?: number | null;
  category?: string | null;
  url?: string;
}

export interface HistoryPage {
  total: number;
  page: number;
  page_size: number;
  items: HistoryItem[];
}

export interface TagSuggestion {
  namespace: string | null;
  name: string;
  display: string | null;
  usage_count: number;
}

export interface TagFacet {
  namespace: string;
  total: number;
}

export interface TagSearchPage {
  total: number;
  page: number;
  page_size: number;
  facets: TagFacet[];
  items: TagSuggestion[];
}

/** Query parameters accepted by `GET /api/galleries` (empty values omitted). */
function queryString(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export function fetchGalleries(
  query: GalleryQuery,
  signal?: AbortSignal,
): Promise<GalleryPage> {
  return request<GalleryPage>({
    method: "GET",
    path: `/api/galleries?${queryString(query as Record<string, unknown>)}`,
  }, { signal });
}

export function fetchRandomGallery(signal?: AbortSignal): Promise<{ id: number }> {
  return request<{ id: number }>({ method: "GET", path: "/api/galleries/random" }, { signal });
}

export function fetchHistory(
  page = 1,
  pageSize = 8,
  signal?: AbortSignal,
): Promise<HistoryPage> {
  return request<HistoryPage>({
    method: "GET",
    path: `/api/history?${queryString({ page, page_size: pageSize })}`,
  }, { signal });
}

/**
 * Tag autocomplete. The backend exposes this as GET /api/tags/search
 * (legacy calls it with `q`, `page_size=8` and `zh=1` for CJK input).
 */
export function fetchTagSuggestions(
  q: string,
  signal?: AbortSignal,
): Promise<TagSearchPage> {
  const isCjk = /[\u3400-\u9fff\uf900-\ufaff]/u.test(q);
  return request<TagSearchPage>({
    method: "GET",
    path: `/api/tags/search?${queryString({
      q,
      page_size: 8,
      ...(isCjk ? { zh: 1 } : {}),
    })}`,
  }, { signal });
}

/** Namespace facets for the browse tag strip (one row is enough). */
export function fetchTagFacets(signal?: AbortSignal): Promise<TagSearchPage> {
  return request<TagSearchPage>({
    method: "GET",
    path: `/api/tags/search?${queryString({ page: 1, page_size: 1 })}`,
  }, { signal });
}

/** Thumbnail path for history/continue-reading items. */
export function galleryThumbUrl(id: number, page = 0): string {
  return `/api/galleries/${id}/thumb/${page}`;
}
