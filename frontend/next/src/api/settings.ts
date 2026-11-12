import { ep, request } from "./client";

export const settingsEp = ep("GET", "/api/settings");
export const saveSettingsEp = ep("POST", "/api/settings");
export const cookieHealthEp = ep("GET", "/api/settings/cookie-health");
export const testExhentaiEp = ep("POST", "/api/settings/exhentai/test");
export const storageInfoEp = ep("GET", "/api/system/storage");
export const thumbsStatusEp = ep("GET", "/api/thumbs/status");
export const generateThumbsEp = ep("POST", "/api/thumbs/generate");
export const testTelegramEp = ep("POST", "/api/telegram/test");
export const tagSearchStatusEp = ep("GET", "/api/tags/search/status");
export const tagSyncStartEp = ep("POST", "/api/tag-sync/start");
export const translationReloadEp = ep("POST", "/api/tags/search/reload");
export const repairCategoriesEp = ep("POST", "/api/tag-sync/repair-categories");
export const apiTokenEp = ep("GET", "/api/auth/api-token");
export const createApiTokenEp = ep("POST", "/api/auth/api-token");
export const revokeApiTokenEp = ep("DELETE", "/api/auth/api-token");

export type AppSettings = Record<string, unknown>;

export interface CookieHealth {
  state?: string;
  message?: string;
  checked_at?: string;
}

export interface ThumbsStatus {
  running?: boolean;
  completed_at?: string | null;
  succeeded?: number;
  failed?: number;
  processed?: number;
  total?: number | null;
}

export interface TagSearchStatus {
  ok?: boolean;
  last_error?: string | null;
  interval_minutes?: number;
  entries?: number;
  updated_at?: string | null;
}

export interface ApiTokenStatus {
  configured: boolean;
  created_at?: string | null;
}

export interface StoragePathInfo {
  path?: string | null;
  bytes?: number | null;
  computed_at?: string | null;
  stale?: boolean;
  computing?: boolean;
  gallery_count?: number;
  image_count?: number;
  thumbnail_count?: number;
}

export interface StorageLargestItem {
  id: number;
  title: string;
  storage_size?: number;
  file_count?: number;
}

export interface StorageInfo {
  library?: StoragePathInfo;
  cold?: StoragePathInfo;
  downloads?: StoragePathInfo;
  cache?: StoragePathInfo;
  largest?: StorageLargestItem[];
}

export function fetchSettings(): Promise<AppSettings> {
  return request<AppSettings>(settingsEp);
}

/**
 * Partial save: the backend merges into `user_settings`
 * (inv-settings.md §G). `password` is only attached for the 428 confirmation of
 * security-sensitive keys; the value never leaves this call.
 */
export function saveSettings(
  payload: Record<string, unknown>,
  password = "",
): Promise<AppSettings | null> {
  return request<AppSettings | null>(saveSettingsEp, {
    body: password ? { ...payload, current_password: password } : payload,
  });
}

export function fetchCookieHealth(): Promise<CookieHealth> {
  return request<CookieHealth>(cookieHealthEp);
}

export function testExhentai(): Promise<{ status?: string; message?: string }> {
  return request<{ status?: string; message?: string }>(testExhentaiEp, { body: {} });
}

export function fetchStorage(): Promise<StorageInfo> {
  return request<StorageInfo>(storageInfoEp);
}

export function fetchThumbsStatus(): Promise<ThumbsStatus> {
  return request<ThumbsStatus>(thumbsStatusEp);
}

export function generateThumbnails(): Promise<{ queued?: number }> {
  return request<{ queued?: number }>(generateThumbsEp, { body: {} });
}

export function testTelegram(): Promise<{ ok?: boolean; results?: unknown }> {
  return request<{ ok?: boolean; results?: unknown }>(testTelegramEp, { body: {} });
}

export function fetchTagSearchStatus(): Promise<TagSearchStatus> {
  return request<TagSearchStatus>(tagSearchStatusEp);
}

export function startTagSync(): Promise<{ queued?: number }> {
  return request<{ queued?: number }>(tagSyncStartEp, { body: {} });
}

export function reloadTagTranslation(): Promise<{ ok?: boolean; last_error?: string | null }> {
  return request<{ ok?: boolean; last_error?: string | null }>(translationReloadEp, {
    body: {},
  });
}

export function repairTagCategories(): Promise<{ repaired?: number; total?: number }> {
  return request<{ repaired?: number; total?: number }>(repairCategoriesEp, { body: {} });
}

export function fetchApiTokenStatus(): Promise<ApiTokenStatus> {
  return request<ApiTokenStatus>(apiTokenEp);
}

/** The plaintext token is returned exactly once, by this call only. */
export function createApiToken(): Promise<{ token: string }> {
  return request<{ token: string }>(createApiTokenEp, { body: {} });
}

export function revokeApiToken(): Promise<null> {
  return request<null>(revokeApiTokenEp, { body: {} });
}
