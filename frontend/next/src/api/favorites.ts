import { ep } from "./client";

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
