import { ep, request } from "./client";
import {
  deleteGalleriesBulkEp,
  deleteGalleriesFilteredEp,
  galleriesEp,
  galleryThumbEp,
  randomGalleryEp,
} from "./galleries";
import { addFavoritesEp } from "./favorites";

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
  /** Total tag count when the response was truncated by `tags_limit`. */
  tag_count?: number | null;
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
  /** Online cards only: quick-action seed state (merged with the stores). */
  in_library?: boolean;
  download_status?: string | null;
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

function withQuery<M extends "GET">(endpoint: { method: M; path: string }, params: Record<string, unknown>): { method: M; path: string } {
  const query = queryString(params);
  return { method: endpoint.method, path: query ? `${endpoint.path}?${query}` : endpoint.path };
}

export function fetchGalleries(
  query: GalleryQuery,
  signal?: AbortSignal,
): Promise<GalleryPage> {
  return request<GalleryPage>(
    withQuery(galleriesEp, query as Record<string, unknown>),
    { signal },
  );
}

export function fetchRandomGallery(signal?: AbortSignal): Promise<{ id: number }> {
  return request<{ id: number }>(randomGalleryEp, { signal });
}

export function fetchHistory(
  page = 1,
  pageSize = 8,
  signal?: AbortSignal,
): Promise<HistoryPage> {
  return request<HistoryPage>(
    withQuery(historyEp, { page, page_size: pageSize }),
    { signal },
  );
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
  return request<TagSearchPage>(
    withQuery(tagsSearchEp, {
      q,
      page_size: 8,
      ...(isCjk ? { zh: 1 } : {}),
    }),
    { signal },
  );
}

/** Namespace facets for the browse tag strip (one row is enough). */
export function fetchTagFacets(signal?: AbortSignal): Promise<TagSearchPage> {
  return request<TagSearchPage>(
    withQuery(tagsSearchEp, { page: 1, page_size: 1 }),
    { signal },
  );
}

/** Thumbnail path for history/continue-reading items. */
export function galleryThumbUrl(id: number, page = 0): string {
  return galleryThumbEp.path
    .replace("{id}", String(id))
    .replace("{id}", String(page));
}

/* ------------------------------------------------------- library management */

export interface SavedSearch {
  id: string;
  name: string;
  query: Record<string, string>;
}

export interface SavedSearchList {
  items: SavedSearch[];
}

export interface BulkDeleteResult {
  deleted: number;
  trashed?: number;
  failed_deletions?: string[];
}

export interface FilteredDeletePayload {
  q?: string;
  category?: string;
  tags?: string;
  tag_mode?: string;
  tag_match?: string;
  delete_files?: boolean;
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
  /** Second-phase guard: only set after the server asked for confirmation. */
  confirm?: boolean;
  match_count?: number;
}

export interface FavoriteAddItem {
  gid: number;
  token?: string;
  title?: string;
}

export interface FavoriteAddBatchResult {
  cloud_ok: boolean;
  cloud_failed: number[];
  successful_gids: number[];
  local_added: number;
}

export async function fetchSavedSearches(signal?: AbortSignal): Promise<SavedSearch[]> {
  const data = await request<SavedSearchList>(savedSearchesEp, { signal });
  return Array.isArray(data?.items) ? data.items : [];
}

export function createSavedSearch(
  name: string,
  query: Record<string, string>,
  signal?: AbortSignal,
): Promise<SavedSearch> {
  return request<SavedSearch>(createSavedSearchEp, {
    body: { name, query },
    signal,
  });
}

export function deleteSavedSearch(id: string, signal?: AbortSignal): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(
    { method: deleteSavedSearchEp.method, path: deleteSavedSearchEp.path.replace("{id}", encodeURIComponent(id)) },
    { signal },
  );
}

export function deleteGalleriesBulk(
  ids: number[],
  deleteFiles: boolean,
  signal?: AbortSignal,
): Promise<BulkDeleteResult> {
  return request<BulkDeleteResult>(deleteGalleriesBulkEp, {
    body: { ids, delete_files: deleteFiles },
    signal,
  });
}

export function deleteGalleriesFiltered(
  payload: FilteredDeletePayload,
  signal?: AbortSignal,
): Promise<BulkDeleteResult> {
  return request<BulkDeleteResult>(deleteGalleriesFilteredEp, {
    body: payload,
    signal,
  });
}

/**
 * Batch favourite add (25 per request, same chunk size as the legacy client).
 * The caller must use `successful_gids` — never the request list — to update UI.
 */
export async function addGalleriesToFavorites(
  items: FavoriteAddItem[],
  targetFavcat: number,
  signal?: AbortSignal,
): Promise<FavoriteAddBatchResult> {
  const chunkSize = 25;
  const failed: number[] = [];
  const successful: number[] = [];
  let localAdded = 0;
  let cloudOk = true;
  for (let index = 0; index < items.length; index += chunkSize) {
    const chunk = items.slice(index, index + chunkSize);
    const data = await request<{
      cloud_ok?: boolean;
      cloud_failed?: number[];
      successful_gids?: number[];
      local_added?: number;
    }>(addFavoritesEp, {
      body: { items: chunk, target_favcat: targetFavcat },
      signal,
    });
    cloudOk = cloudOk && Boolean(data?.cloud_ok);
    if (Array.isArray(data?.cloud_failed)) failed.push(...data.cloud_failed);
    if (Array.isArray(data?.successful_gids)) successful.push(...data.successful_gids);
    localAdded += Number(data?.local_added) || 0;
  }
  return {
    cloud_ok: cloudOk,
    cloud_failed: failed,
    successful_gids: successful,
    local_added: localAdded,
  };
}
