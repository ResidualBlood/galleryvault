import { ep, request } from "./client";

/* ------------------------------------------------------------ notifications */

export const notificationsEp = ep("GET", "/api/notifications");
export const readNotificationsEp = ep("POST", "/api/notifications/read");
export const clearNotificationsEp = ep("POST", "/api/notifications/clear");

export interface NotificationItem {
  id: number;
  kind?: string;
  title: string;
  detail?: string;
  created_at?: string;
  read?: boolean;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count?: number;
  /** Legacy field kept for callers written before the backend settled on unread_count. */
  unread?: number;
}

export function getNotifications(signal?: AbortSignal): Promise<NotificationList> {
  return request<NotificationList>(notificationsEp, { signal });
}

export function markNotificationsRead(): Promise<NotificationList> {
  return request<NotificationList>(readNotificationsEp, { body: {} });
}

export function clearNotifications(): Promise<NotificationList> {
  return request<NotificationList>(clearNotificationsEp, { body: {} });
}

/* ------------------------------------------------------------ task activity */

export const logsEp = ep("GET", "/api/logs");
export const cancelLogTaskEp = ep("POST", "/api/logs/{id}/cancel");

export interface RunningTask {
  task: string;
  started_at?: string | null;
  done?: number | null;
  total?: number | null;
  stage?: string | null;
  cancellable?: boolean;
}

export interface FinishedTask {
  task: string;
  status?: string;
  reason?: string;
  started_at?: string | null;
  completed_at?: string | null;
  done?: number | null;
  total?: number | null;
}

export interface BackgroundLogs {
  running?: RunningTask[];
  finished?: FinishedTask[];
}

export function fetchBackgroundLogs(signal?: AbortSignal): Promise<BackgroundLogs> {
  return request<BackgroundLogs>(logsEp, { signal });
}

export function cancelBackgroundTask(task: string): Promise<unknown> {
  return request<unknown>({ method: cancelLogTaskEp.method, path: cancelLogTaskEp.path.replace("{id}", encodeURIComponent(task)) }, { body: {} });
}

/* ---------------------------------------------------------------- syslog */

export const systemLogsEp = ep("GET", "/api/system/logs");
export const downloadSystemLogsEp = ep("GET", "/api/system/logs/download");
export const setLogLevelEp = ep("POST", "/api/system/logs/level");
export const clearSystemLogsEp = ep("DELETE", "/api/system/logs");

export interface SystemLogEntry {
  id: number;
  time: string;
  level: string;
  logger: string;
  message: string;
  request_id?: string | null;
  context?: Record<string, unknown> | null;
  exception?: string | null;
  exception_type?: string | null;
}

export interface SystemLogPage {
  level?: string;
  log_mode?: string;
  log_file?: string | null;
  logs: SystemLogEntry[];
}

export interface SystemLogQuery {
  minLevel?: string;
  search?: string;
  limit?: number;
}

export function fetchSystemLogs(
  query: SystemLogQuery = {},
  signal?: AbortSignal,
): Promise<SystemLogPage> {
  const params = new URLSearchParams();
  if (query.minLevel) params.set("min_level", query.minLevel);
  if (query.search) params.set("search", query.search);
  params.set("limit", String(query.limit ?? 200));
  return request<SystemLogPage>(
    { method: systemLogsEp.method, path: `${systemLogsEp.path}?${params.toString()}` },
    { signal },
  );
}

export function systemLogsDownloadUrl(): string {
  return downloadSystemLogsEp.path;
}

export function setSystemLogLevel(level: string): Promise<{ level?: string }> {
  return request<{ level?: string }>(setLogLevelEp, { body: { level } });
}

export function clearSystemLogs(): Promise<{ status?: string }> {
  return request<{ status?: string }>(clearSystemLogsEp);
}

/* ------------------------------------------------------- global controls */

export const scanStatusEp = ep("GET", "/api/scan");
export const triggerScanEp = ep("POST", "/api/scan");
export const pauseEp = ep("GET", "/api/pause");
export const setPauseEp = ep("POST", "/api/pause");
export const purgeArchivedSourcesEp = ep("POST", "/api/system/purge-archived-sources");

export interface ScanState {
  running?: boolean;
  status?: string;
  last?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export function fetchScanStatus(signal?: AbortSignal): Promise<ScanState> {
  return request<ScanState>(scanStatusEp, { signal });
}

export function triggerScan(): Promise<{ status?: string; detail?: string }> {
  return request<{ status?: string; detail?: string }>(triggerScanEp, { body: {} });
}

export function fetchPause(): Promise<{ paused: boolean }> {
  return request<{ paused: boolean }>(pauseEp);
}

export function setPaused(paused: boolean): Promise<{ paused: boolean }> {
  return request<{ paused: boolean }>(setPauseEp, { body: { paused } });
}

export function purgeArchivedSources(): Promise<{ status?: string }> {
  return request<{ status?: string }>(purgeArchivedSourcesEp, { body: {} });
}
