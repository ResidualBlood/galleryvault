import { ep, request } from "./client";

export const notificationsEp = ep("GET", "/api/notifications");
export const readNotificationsEp = ep("POST", "/api/notifications/read");
export const clearNotificationsEp = ep("POST", "/api/notifications/clear");
export const logsEp = ep("GET", "/api/logs");
export const cancelLogTaskEp = ep("POST", "/api/logs/{id}/cancel");
export const cancelArchiveLogEp = ep("POST", "/api/logs/archive/cancel");
export const systemLogsEp = ep("GET", "/api/system/logs");
export const downloadSystemLogsEp = ep("GET", "/api/system/logs/download");
export const setLogLevelEp = ep("POST", "/api/system/logs/level");
export const clearSystemLogsEp = ep("DELETE", "/api/system/logs");
export const archiveEp = ep("GET", "/api/archive");
export const createArchiveEp = ep("POST", "/api/archive");
export const previewArchiveEp = ep("POST", "/api/archives/preview");
export const purgeArchivedSourcesEp = ep(
  "POST",
  "/api/system/purge-archived-sources",
);

export interface NotificationSummary {
  items?: unknown[];
  unread?: number;
}

export function getNotifications(): Promise<NotificationSummary> {
  return request<NotificationSummary>(notificationsEp);
}
