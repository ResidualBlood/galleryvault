import { ep, request } from "./client";

export const favoriteCategoriesEp = ep("GET", "/api/favorites/categories");
export const favoriteItemsEp = ep("GET", "/api/favorites/{id}/items");
export const checkFavoriteCategoryEp = ep("POST", "/api/favorites/{id}/check");
export const addFavoritesEp = ep("POST", "/api/favorites/add");
export const moveFavoritesEp = ep("POST", "/api/favorites/move");
export const removeFavoritesEp = ep("POST", "/api/favorites/remove");
export const favoriteNoteEp = ep("POST", "/api/favorites/note");
export const syncFavoriteCategoriesEp = ep(
  "POST",
  "/api/favorites/sync-categories",
);
export const checkAllFavoritesEp = ep("POST", "/api/favorites/check-all");
export const favoriteCheckStatusEp = ep("GET", "/api/favorites/check-status");
export const downloadMissingFavoritesEp = ep(
  "POST",
  "/api/favorites/download-missing",
);
export const downloadSelectedFavoritesEp = ep(
  "POST",
  "/api/favorites/download-selected",
);
export const saveFavoriteMonitorSettingsEp = ep("POST", "/api/settings");

/* --------------------------------------------------- favorite duplicates */

export const favoriteDuplicatesStatusEp = ep(
  "GET",
  "/api/favorites/duplicates/status",
);
export const scanFavoriteDuplicatesEp = ep(
  "POST",
  "/api/favorites/duplicates/scan",
);
export const ignoreFavoriteDuplicateEp = ep(
  "POST",
  "/api/favorites/duplicates/ignore",
);
export const unignoreFavoriteDuplicateEp = ep(
  "DELETE",
  "/api/favorites/duplicates/ignore",
);
export const ignoredFavoriteDuplicatesEp = ep(
  "GET",
  "/api/favorites/duplicates/ignored",
);

/* ------------------------------------------------------------ quick actions */

export interface FavoriteCategory {
  favcat: number;
  name: string;
  cloud_count?: number | null;
  local_count?: number | null;
  cloud_size?: number | null;
  local_size?: number | null;
  enabled?: boolean | null;
  mode?: string | null;
  poll_interval_minutes?: number | null;
}

export interface FavoriteItemTag {
  namespace: string | null;
  name: string;
  display?: string | null;
}

export interface FavoriteItem {
  favcat: number;
  gid: number;
  token: string;
  title: string;
  title_jpn: string | null;
  url: string | null;
  gallery_id: number | null;
  category: string | null;
  page_count: number | null;
  cover_url: string | null;
  file_size: number | null;
  note: string | null;
  is_local: boolean;
  tags: FavoriteItemTag[];
}

export interface FavoriteItemsPage {
  total: number;
  page: number;
  page_size: number;
  state: string;
  items: FavoriteItem[];
}

export interface FavoriteCheckCategory {
  running?: boolean;
  done?: number;
  total?: number;
  error?: string | null;
  started?: string | null;
}

export interface FavoriteCheckStatus {
  running: boolean;
  categories: Record<string, FavoriteCheckCategory>;
  last_error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface FavoriteMonitorSetting {
  favcat: number;
  enabled: boolean;
  mode: string;
  poll_interval_minutes: number;
}

export interface FavoriteDownloadResult {
  queued: number;
  skipped: number;
}

export interface FavoriteMutationResult {
  gids: number[];
  target_favcat?: number;
  cloud_ok: boolean;
  cloud_failed: number[];
  successful_gids: number[];
  cloud_added?: number;
  cloud_moved?: number;
  cloud_removed?: number;
  local_added?: number;
  local_moved?: number;
  local_removed?: number;
}

export interface FavoriteNoteResult {
  gid: number;
  cloud_ok: boolean;
  local_updated: number;
  note: string | null;
}

export interface AddFavoriteInput {
  gid: number;
  token: string;
  target_favcat: number;
  note?: string;
}

function gidListBody(gids: number[]): { gids: number[] } {
  return { gids: gids.map((gid) => Math.trunc(gid)).filter((gid) => gid > 0) };
}

/**
 * Cloud-first favorite mutations.
 *
 * The backend only writes local state for `successful_gids`; callers must use
 * that field (never the request arguments) to update UI state. See
 * PLAN-frontend-rewrite §4.1 and inv-backend.md §3.
 */
export async function fetchFavoriteCategories(
  signal?: AbortSignal,
): Promise<FavoriteCategory[]> {
  const data = await request<FavoriteCategory[]>(favoriteCategoriesEp, { signal });
  if (!Array.isArray(data)) return [];
  return data
    .filter((item) => Number.isInteger(item?.favcat) && item.favcat >= 0 && item.favcat <= 9)
    .map((item) => ({
      favcat: item.favcat,
      name: typeof item.name === "string" ? item.name : "",
      cloud_count: typeof item.cloud_count === "number" ? item.cloud_count : null,
      local_count: typeof item.local_count === "number" ? item.local_count : null,
      cloud_size: typeof item.cloud_size === "number" ? item.cloud_size : null,
      local_size: typeof item.local_size === "number" ? item.local_size : null,
      enabled: item.enabled ?? null,
      mode: item.mode ?? null,
      poll_interval_minutes:
        typeof item.poll_interval_minutes === "number"
          ? item.poll_interval_minutes
          : null,
    }))
    .sort((a, b) => a.favcat - b.favcat);
}

export async function addFavorite(
  input: AddFavoriteInput,
  signal?: AbortSignal,
): Promise<FavoriteMutationResult> {
  const data = await request<FavoriteMutationResult>(addFavoritesEp, {
    body: {
      gid: input.gid,
      token: input.token,
      target_favcat: input.target_favcat,
      note: input.note ?? "",
    },
    signal,
  });
  return {
    ...data,
    cloud_ok: Boolean(data?.cloud_ok),
    cloud_failed: Array.isArray(data?.cloud_failed) ? data.cloud_failed : [],
    successful_gids: Array.isArray(data?.successful_gids) ? data.successful_gids : [],
    gids: Array.isArray(data?.gids) ? data.gids : [input.gid],
  };
}

export async function moveFavorite(
  gids: number[],
  targetFavcat: number,
  signal?: AbortSignal,
): Promise<FavoriteMutationResult> {
  const data = await request<FavoriteMutationResult>(moveFavoritesEp, {
    body: { ...gidListBody(gids), target_favcat: targetFavcat },
    signal,
  });
  return {
    ...data,
    cloud_ok: Boolean(data?.cloud_ok),
    cloud_failed: Array.isArray(data?.cloud_failed) ? data.cloud_failed : [],
    successful_gids: Array.isArray(data?.successful_gids)
      ? data.successful_gids
      : Array.isArray(data?.cloud_failed)
        ? gidListBody(gids).gids.filter((gid) => !data.cloud_failed.includes(gid))
        : [],
    gids: Array.isArray(data?.gids) ? data.gids : gidListBody(gids).gids,
  };
}

export async function removeFavorite(
  gids: number[],
  signal?: AbortSignal,
): Promise<FavoriteMutationResult> {
  const data = await request<FavoriteMutationResult>(removeFavoritesEp, {
    body: gidListBody(gids),
    signal,
  });
  return {
    ...data,
    cloud_ok: Boolean(data?.cloud_ok),
    cloud_failed: Array.isArray(data?.cloud_failed) ? data.cloud_failed : [],
    successful_gids: Array.isArray(data?.successful_gids)
      ? data.successful_gids
      : Array.isArray(data?.cloud_failed)
        ? gidListBody(gids).gids.filter((gid) => !data.cloud_failed.includes(gid))
        : [],
    gids: Array.isArray(data?.gids) ? data.gids : gidListBody(gids).gids,
  };
}

export async function setFavoriteNote(
  gid: number,
  note: string,
  signal?: AbortSignal,
): Promise<FavoriteNoteResult> {
  const data = await request<FavoriteNoteResult>(favoriteNoteEp, {
    body: { gid, note },
    signal,
  });
  return {
    gid: typeof data?.gid === "number" ? data.gid : gid,
    cloud_ok: Boolean(data?.cloud_ok),
    local_updated: Number(data?.local_updated) || 0,
    note: typeof data?.note === "string" ? data.note : null,
  };
}

/* ---------------------------------------------------------- monitor / list */

function favoriteItemPath(favcat: number, params: URLSearchParams): string {
  const suffix = params.toString();
  const path = favoriteItemsEp.path.replace("{id}", String(favcat));
  return suffix ? `${path}?${suffix}` : path;
}

function normalizeFavoriteItem(raw: FavoriteItem): FavoriteItem {
  return {
    favcat: Number(raw?.favcat) || 0,
    gid: Number(raw?.gid) || 0,
    token: typeof raw?.token === "string" ? raw.token : "",
    title: typeof raw?.title === "string" ? raw.title : "",
    title_jpn: typeof raw?.title_jpn === "string" ? raw.title_jpn : null,
    url: typeof raw?.url === "string" ? raw.url : null,
    gallery_id:
      typeof raw?.gallery_id === "number" && raw.gallery_id > 0 ? raw.gallery_id : null,
    category: typeof raw?.category === "string" ? raw.category : null,
    page_count: typeof raw?.page_count === "number" ? raw.page_count : null,
    cover_url: typeof raw?.cover_url === "string" ? raw.cover_url : null,
    file_size: typeof raw?.file_size === "number" ? raw.file_size : null,
    note: typeof raw?.note === "string" ? raw.note : null,
    is_local: Boolean(raw?.is_local) || typeof raw?.gallery_id === "number",
    tags: Array.isArray(raw?.tags)
      ? raw.tags.map((tag) => ({
          namespace: typeof tag?.namespace === "string" ? tag.namespace : null,
          name: typeof tag?.name === "string" ? tag.name : "",
          display: typeof tag?.display === "string" ? tag.display : null,
        }))
      : [],
  };
}

/** One page of a favourite folder; callers build `params` with buildFavListParams. */
export async function fetchFavoriteItems(
  favcat: number,
  params: URLSearchParams,
  signal?: AbortSignal,
): Promise<FavoriteItemsPage> {
  const data = await request<FavoriteItemsPage>(
    { method: favoriteItemsEp.method, path: favoriteItemPath(favcat, params) },
    { signal },
  );
  return {
    total: Number(data?.total) || 0,
    page: Number(data?.page) || 1,
    page_size: Number(data?.page_size) || 0,
    state: typeof data?.state === "string" ? data.state : "all",
    items: Array.isArray(data?.items) ? data.items.map(normalizeFavoriteItem) : [],
  };
}

export async function checkFavoriteCategory(
  favcat: number,
  signal?: AbortSignal,
): Promise<void> {
  const path = checkFavoriteCategoryEp.path.replace("{id}", String(favcat));
  await request({ method: checkFavoriteCategoryEp.method, path }, { signal });
}

export async function checkAllFavorites(signal?: AbortSignal): Promise<number[]> {
  const data = await request<{ favcats?: number[] }>(checkAllFavoritesEp, { signal });
  return Array.isArray(data?.favcats) ? data.favcats : [];
}

export async function syncFavoriteCategoryNames(signal?: AbortSignal): Promise<void> {
  await request(syncFavoriteCategoriesEp, { signal });
}

export async function downloadMissingFavorites(signal?: AbortSignal): Promise<number[]> {
  const data = await request<{ favcats?: number[] }>(downloadMissingFavoritesEp, {
    signal,
  });
  return Array.isArray(data?.favcats) ? data.favcats : [];
}

export async function fetchFavoriteCheckStatus(
  signal?: AbortSignal,
): Promise<FavoriteCheckStatus> {
  const data = await request<FavoriteCheckStatus>(favoriteCheckStatusEp, { signal });
  const categories: Record<string, FavoriteCheckCategory> = {};
  for (const [key, value] of Object.entries(data?.categories ?? {})) {
    if (!value || typeof value !== "object") continue;
    categories[key] = {
      running: Boolean(value.running),
      done: Number(value.done) || 0,
      total: Number(value.total) || 0,
      error: typeof value.error === "string" ? value.error : null,
      started: typeof value.started === "string" ? value.started : null,
    };
  }
  return {
    running: Boolean(data?.running),
    categories,
    last_error: typeof data?.last_error === "string" ? data.last_error : null,
    started_at: typeof data?.started_at === "string" ? data.started_at : null,
    completed_at: typeof data?.completed_at === "string" ? data.completed_at : null,
  };
}

export async function saveFavoriteMonitorSettings(
  favorites: FavoriteMonitorSetting[],
  signal?: AbortSignal,
): Promise<void> {
  await request(saveFavoriteMonitorSettingsEp, {
    body: {
      favorites: favorites.map((item) => ({
        favcat: item.favcat,
        enabled: item.enabled,
        mode: item.mode,
        poll_interval_minutes: Math.max(1, Math.trunc(item.poll_interval_minutes) || 720),
      })),
    },
    signal,
  });
}

export interface FavoriteDownloadOptions {
  quality?: "original" | "resample";
  archive?: boolean;
}

export async function downloadSelectedFavorites(
  gids: number[],
  options: FavoriteDownloadOptions = {},
  signal?: AbortSignal,
): Promise<FavoriteDownloadResult> {
  const body: Record<string, unknown> = { ...gidListBody(gids) };
  if (options.quality) body.quality = options.quality;
  if (options.archive) body.archive = true;
  const data = await request<FavoriteDownloadResult>(downloadSelectedFavoritesEp, {
    body,
    signal,
  });
  return {
    queued: Number(data?.queued) || 0,
    skipped: Number(data?.skipped) || 0,
  };
}
