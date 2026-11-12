import { ep } from "./client";

export const downloadsEp = ep("GET", "/api/downloads");
export const createDownloadEp = ep("POST", "/api/downloads");
export const createDownloadBatchEp = ep("POST", "/api/downloads/batch");
export const cancelDownloadEp = ep("POST", "/api/downloads/{id}/cancel");
export const retryDownloadEp = ep("POST", "/api/downloads/{id}/retry");
export const deleteDownloadEp = ep("DELETE", "/api/downloads/{id}");
export const clearSuccessfulDownloadsEp = ep(
  "POST",
  "/api/downloads/clear-success",
);
export const retryAllDownloadsEp = ep("POST", "/api/downloads/retry-all");
export const quotaEp = ep("GET", "/api/quota");
export const pauseEp = ep("GET", "/api/pause");
export const setPauseEp = ep("POST", "/api/pause");
