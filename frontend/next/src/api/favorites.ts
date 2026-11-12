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
  enabled?: boolean | null;
  mode?: string | null;
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
      enabled: item.enabled ?? null,
      mode: item.mode ?? null,
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
    successful_gids: Array.isArray(data?.cloud_failed)
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
    successful_gids: Array.isArray(data?.cloud_failed)
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
