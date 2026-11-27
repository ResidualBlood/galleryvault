import { ep, request } from "./client";

export const archiveEp = ep("GET", "/api/archive");
export const createArchiveEp = ep("POST", "/api/archive");
export const restoreArchivesEp = ep("POST", "/api/archive/restore");
export const cancelArchiveEp = ep("POST", "/api/logs/archive/cancel");
export const previewArchiveEp = ep("POST", "/api/archives/preview");

export interface ArchiveState {
  running?: boolean;
  done?: number;
  total?: number;
  skipped?: number;
  failed?: number;
  last_error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ArchivePreviewItem {
  gid: number;
  title?: string;
  error?: string;
  resample_cost?: number | null;
  resample_size?: number | null;
  original_cost?: number | null;
  original_size?: number | null;
  resample_available?: boolean;
  original_available?: boolean;
}

export interface ArchivePreview {
  funds?: number | null;
  items?: ArchivePreviewItem[];
}

export function fetchArchiveState(signal?: AbortSignal): Promise<ArchiveState> {
  return request<ArchiveState>(archiveEp, { signal });
}

export function startArchive(): Promise<{ status?: string; detail?: string }> {
  return request<{ status?: string; detail?: string }>(createArchiveEp, { body: {} });
}

export interface RestoreReply {
  status?: string;
  total?: number;
  detail?: string;
}

/** Move the selected cold galleries back to the download root (background). */
export function restoreArchives(ids: number[]): Promise<RestoreReply> {
  return request<RestoreReply>(restoreArchivesEp, { body: { ids } });
}

export function cancelArchive(): Promise<{ status?: string }> {
  return request<{ status?: string }>(cancelArchiveEp, { body: {} });
}

export function previewArchive(
  gids: number[],
  signal?: AbortSignal,
): Promise<ArchivePreview> {
  return request<ArchivePreview>(previewArchiveEp, { body: { gids }, signal });
}
