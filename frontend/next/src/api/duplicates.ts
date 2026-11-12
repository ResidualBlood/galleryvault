import { ep, request } from "./client";

/* ----------------------------------------------------- library duplicate scan */

export const libraryScanEp = ep("POST", "/api/scan");
export const libraryScanStatusEp = ep("GET", "/api/scan");
export const libraryDuplicatesEp = ep("GET", "/api/scan/duplicates");
export const resolveDuplicateEp = ep("POST", "/api/scan/duplicates/{gid}/resolve");
export const duplicateStatusEp = ep("POST", "/api/scan/duplicates/{gid}/{status}");
export const duplicateThumbEp = ep("GET", "/api/scan/duplicates/thumb/{key}");

/* --------------------------------------------------------- cross-gid groups */

export const crossGidDuplicatesEp = ep("GET", "/api/library/duplicates/cross-gid");
export const refreshCrossGidDuplicatesEp = ep(
  "POST",
  "/api/library/duplicates/cross-gid/refresh",
);

/* ------------------------------------------------------ favorite duplicates */

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

/* ---------------------------------------------------------- favorite removal */

export const removeFavoritesEp = ep("POST", "/api/favorites/remove");

export interface DuplicateTag {
  namespace: string | null;
  name: string;
  display?: string | null;
}

export interface LibraryDuplicateCopy {
  path: string;
  key: string;
  gallery_id: number | null;
  storage_type?: string | null;
  title?: string | null;
  title_jpn?: string | null;
  display_title?: string | null;
  page_count?: number | null;
  file_size?: number | null;
  posted_at?: string | null;
  is_current?: boolean;
  is_starred?: boolean;
  rating?: number;
  has_custom_tags?: boolean;
  tags?: DuplicateTag[];
}

export interface LibraryDuplicateGroup {
  gid: number;
  status: "open" | "dismissed" | string;
  policy?: string | null;
  winner_path?: string | null;
  copies: LibraryDuplicateCopy[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LibraryDuplicatesResponse {
  groups: LibraryDuplicateGroup[];
  count: number;
}

export interface ResolveDuplicateResult extends LibraryDuplicatesResponse {
  failed_paths?: string[];
}

export interface FavoriteDuplicateItem {
  gid: number;
  title?: string | null;
  title_jpn?: string | null;
  display_title?: string | null;
  url?: string | null;
  token?: string | null;
  favcat?: number | null;
  gallery_id?: number | null;
  file_size?: number | null;
  posted_at?: string | null;
  cover_url?: string | null;
  cover_data?: string | null;
  favorited?: boolean;
  tags?: DuplicateTag[];
}

export interface FavoriteDuplicateGroup {
  key: string;
  artist?: string | null;
  items: FavoriteDuplicateItem[];
}

export interface FavoriteDuplicatesStatus {
  running: boolean;
  stage?: string | null;
  done: number;
  total: number;
  last_error?: string | null;
  groups: FavoriteDuplicateGroup[];
  group_count?: number;
  item_count?: number;
  ignored?: IgnoredFavoriteDuplicate[];
}

export interface IgnoredFavoriteDuplicate {
  key: string;
  title?: string | null;
  gids?: number[];
  items: FavoriteDuplicateItem[];
}

export interface CrossGidItem {
  gid: number;
  gallery_id?: number | null;
  title?: string | null;
  title_jpn?: string | null;
  display_title?: string | null;
  url?: string | null;
  token?: string | null;
  favorited?: boolean;
  category?: string | null;
  favcat?: number | null;
  pages?: number | null;
  page_count?: number | null;
  file_size?: number | null;
  storage_type?: string | null;
  cover_url?: string | null;
  cover_data?: string | null;
}

export interface CrossGidGroup {
  key: string;
  artist?: string | null;
  items: CrossGidItem[];
}

export interface CrossGidResponse {
  ready: boolean;
  count: number;
  groups: CrossGidGroup[];
}

export interface RemoveFavoritesResult {
  gids?: number[];
  cloud_ok: boolean;
  cloud_failed?: number[];
  successful_gids?: number[];
  deleted_local_galleries?: number;
  failed_deletions?: string[];
}

export function fetchLibraryDuplicates(
  signal?: AbortSignal,
): Promise<LibraryDuplicatesResponse> {
  return request<LibraryDuplicatesResponse>(libraryDuplicatesEp, { signal });
}

export function startLibraryScan(signal?: AbortSignal): Promise<{ status?: string }> {
  return request<{ status?: string }>(libraryScanEp, { signal });
}

export function fetchLibraryScanStatus(
  signal?: AbortSignal,
): Promise<{ running?: boolean }> {
  return request<{ running?: boolean }>(libraryScanStatusEp, { signal });
}

export function resolveLibraryDuplicate(
  gid: number,
  path: string,
  deleteOthers: boolean,
  signal?: AbortSignal,
): Promise<ResolveDuplicateResult> {
  return request<ResolveDuplicateResult>(
    {
      method: resolveDuplicateEp.method,
      path: resolveDuplicateEp.path
        .replace("{gid}", String(gid))
        .replace("{gid}", String(gid)),
    },
    { body: { path, delete_others: deleteOthers }, signal },
  );
}

export function setLibraryDuplicateStatus(
  gid: number,
  status: "open" | "dismissed",
  signal?: AbortSignal,
): Promise<{ status?: string }> {
  return request<{ status?: string }>(
    {
      method: duplicateStatusEp.method,
      path: duplicateStatusEp.path
        .replace("{gid}", String(gid))
        .replace("{status}", status),
    },
    { signal },
  );
}

export function duplicateThumbPath(key: string): string {
  return duplicateThumbEp.path.replace("{key}", encodeURIComponent(key));
}

export function fetchCrossGidDuplicates(
  signal?: AbortSignal,
): Promise<CrossGidResponse> {
  return request<CrossGidResponse>(crossGidDuplicatesEp, { signal });
}

export function refreshCrossGidDuplicates(
  signal?: AbortSignal,
): Promise<CrossGidResponse> {
  return request<CrossGidResponse>(refreshCrossGidDuplicatesEp, { signal });
}

export function fetchFavoriteDuplicatesStatus(
  signal?: AbortSignal,
): Promise<FavoriteDuplicatesStatus> {
  return request<FavoriteDuplicatesStatus>(favoriteDuplicatesStatusEp, { signal });
}

export function scanFavoriteDuplicates(
  signal?: AbortSignal,
): Promise<{ started?: boolean }> {
  return request<{ started?: boolean }>(scanFavoriteDuplicatesEp, { signal });
}

export function ignoreFavoriteDuplicate(
  body: { key: string; title?: string; gids?: number[] },
  signal?: AbortSignal,
): Promise<unknown> {
  return request(ignoreFavoriteDuplicateEp, { body, signal });
}

export function unignoreFavoriteDuplicate(
  key: string,
  signal?: AbortSignal,
): Promise<unknown> {
  return request(
    {
      method: unignoreFavoriteDuplicateEp.method,
      path: `${unignoreFavoriteDuplicateEp.path}?key=${encodeURIComponent(key)}`,
    },
    { signal },
  );
}

export function fetchIgnoredFavoriteDuplicates(
  signal?: AbortSignal,
): Promise<IgnoredFavoriteDuplicate[]> {
  return request<IgnoredFavoriteDuplicate[]>(ignoredFavoriteDuplicatesEp, { signal });
}

export function removeFavorites(
  gids: number[],
  deleteLocal: boolean,
  signal?: AbortSignal,
): Promise<RemoveFavoritesResult> {
  return request<RemoveFavoritesResult>(removeFavoritesEp, {
    body: { gids, delete_local: deleteLocal },
    signal,
  });
}
