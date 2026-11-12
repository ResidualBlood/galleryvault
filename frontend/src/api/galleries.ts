import { ep } from "./client";

/* ------------------------------------------------------------- galleries */

export const galleriesEp = ep("GET", "/api/galleries");
export const randomGalleryEp = ep("GET", "/api/galleries/random");
export const galleryEp = ep("GET", "/api/galleries/{id}");
export const galleryProgressEp = ep("GET", "/api/galleries/{id}/progress");
export const updateGalleryProgressEp = ep("PUT", "/api/galleries/{id}/progress");
export const nextGalleryEp = ep("GET", "/api/galleries/{id}/next");
export const galleryFavoriteEp = ep("GET", "/api/galleries/{id}/favorite");
export const galleryListsEp = ep("GET", "/api/galleries/{id}/lists");
export const patchGalleryLocalEp = ep("PATCH", "/api/galleries/{id}/local");
export const deleteGalleryEp = ep("DELETE", "/api/galleries/{id}");
export const redownloadGalleryEp = ep("POST", "/api/galleries/{id}/redownload");
export const downloadGalleryOriginalEp = ep(
  "POST",
  "/api/galleries/{id}/download-original",
);
export const syncGalleryTagsEp = ep("POST", "/api/galleries/{id}/sync-tags");
export const deleteGalleriesBulkEp = ep("POST", "/api/galleries/delete-bulk");
export const deleteGalleriesFilteredEp = ep(
  "POST",
  "/api/galleries/delete-filtered",
);
export const trashGalleriesEp = ep("GET", "/api/galleries/trash");
export const expungedGalleriesEp = ep("GET", "/api/galleries/expunged");
export const restoreGalleriesEp = ep("POST", "/api/galleries/restore");
export const purgeGalleriesEp = ep("POST", "/api/galleries/purge");
export const redownloadExpungedEp = ep(
  "POST",
  "/api/galleries/expunged/redownload",
);
export const integrityGalleriesEp = ep("GET", "/api/galleries/integrity");
export const scanIntegrityEp = ep("POST", "/api/galleries/integrity/scan");
export const clearAllProgressEp = ep("DELETE", "/api/galleries/progress");
export const clearGalleryProgressEp = ep(
  "DELETE",
  "/api/galleries/{id}/progress",
);
export const galleryPageEp = ep("GET", "/api/galleries/{id}/pages/{id}");
export const galleryPageMetaEp = ep(
  "GET",
  "/api/galleries/{id}/pages/{id}/meta",
);
export const galleryThumbEp = ep("GET", "/api/galleries/{id}/thumb/{id}");
export const exportGalleryCbzEp = ep("GET", "/api/galleries/{id}/export.cbz");

/* ----------------------------------------------------------- maintenance */

export const scanStatusEp = ep("GET", "/api/scan");
export const startScanEp = ep("POST", "/api/scan");
export const duplicateGroupsEp = ep("GET", "/api/scan/duplicates");
export const resolveDuplicateEp = ep(
  "POST",
  "/api/scan/duplicates/{id}/resolve",
);
export const markDuplicateEp = ep("POST", "/api/scan/duplicates/{id}/{id}");
export const duplicateThumbEp = ep("GET", "/api/scan/duplicates/thumb/{id}");
export const crossGidDuplicatesEp = ep(
  "GET",
  "/api/library/duplicates/cross-gid",
);
export const refreshCrossGidDuplicatesEp = ep(
  "POST",
  "/api/library/duplicates/cross-gid/refresh",
);

/* --------------------------------------------------------------- updates */

export const updatesEp = ep("GET", "/api/updates");
export const ignoredUpdatesEp = ep("GET", "/api/updates/ignored");
export const updatesStatusEp = ep("GET", "/api/updates/status");
export const scanUpdatesEp = ep("POST", "/api/updates/scan");
export const runUpdatesEp = ep("POST", "/api/updates/update");
export const ignoreUpdatesEp = ep("POST", "/api/updates/ignore");
export const unignoreUpdatesEp = ep("POST", "/api/updates/unignore");
export const deleteUpdatesEp = ep("POST", "/api/updates/delete");
