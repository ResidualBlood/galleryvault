import { ep } from "./client";

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
