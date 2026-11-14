import { request } from "./client";
import { abortableDelay } from "./poll";
import { syncGalleryTagsEp } from "./galleries";
import {
  refreshTagCategoriesEp,
  reloadTagsEp,
  startTagSyncEp,
  tagSyncStatusEp,
  tagsSearchEp,
  type TagSearchPage,
} from "./library";

export interface TagsQuery {
  q?: string;
  namespace?: string;
  page?: number;
  page_size?: number;
}

/** The reload endpoint now only acknowledges the spawn (202). */
export interface TagReloadResult {
  accepted: boolean;
}

export interface TagSyncStartResult {
  status?: string;
  queued?: number;
  detail?: string;
}

export interface GalleryTagSyncResult {
  source?: "cache" | "network" | string;
  count?: number;
}

/** Live task-manager state exposed by `GET /api/tag-sync/status`. */
export interface TagSyncStatus {
  running?: boolean;
  total?: number;
  queued?: number;
  processed?: number;
  succeeded?: number;
  failed?: number;
  category_refreshed?: number;
  category_refresh_running?: boolean;
  last_error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff]/u;

export function isCjkQuery(q: string): boolean {
  return CJK_RE.test(q);
}

/**
 * Tag cloud search. Mirrors the legacy page: CJK queries always use page 1
 * with `zh=1` (the translation index returns a single page), and the namespace
 * filter is dropped for those queries.
 */
export function fetchTags(
  query: TagsQuery = {},
  signal?: AbortSignal,
): Promise<TagSearchPage> {
  const q = (query.q ?? "").trim();
  const cjk = isCjkQuery(q);
  const params = new URLSearchParams();
  params.set("page", String(cjk ? 1 : Math.max(1, query.page ?? 1)));
  params.set("page_size", String(Math.max(1, query.page_size ?? 100)));
  if (!cjk && query.namespace) params.set("namespace", query.namespace);
  if (q) params.set("q", q);
  if (cjk && q) params.set("zh", "1");
  return request<TagSearchPage>(
    { method: tagsSearchEp.method, path: `${tagsSearchEp.path}?${params}` },
    { signal },
  );
}

export function reloadTags(signal?: AbortSignal): Promise<TagReloadResult> {
  return request<TagReloadResult>(reloadTagsEp, { signal });
}

export function startTagSync(signal?: AbortSignal): Promise<TagSyncStartResult> {
  return request<TagSyncStartResult>(startTagSyncEp, { signal });
}

export function fetchTagSyncStatus(signal?: AbortSignal): Promise<TagSyncStatus> {
  return request<TagSyncStatus>(tagSyncStatusEp, { signal });
}

/** Start the one-shot category backfill for galleries stuck in `other`. */
export function refreshTagCategories(
  signal?: AbortSignal,
): Promise<{ status?: string }> {
  return request<{ status?: string }>(refreshTagCategoriesEp, { body: {}, signal });
}

const CATEGORY_REFRESH_POLL_MS = 1_500;
const CATEGORY_REFRESH_TIMEOUT_MS = 300_000;

/**
 * Poll `GET /api/tag-sync/status` until `category_refresh_running` flips back
 * to false. The first delay gives the spawned worker time to mark itself
 * running, so a fast no-op refresh is not reported as "already finished".
 */
export async function waitForCategoryRefresh(options: {
  signal?: AbortSignal;
  intervalMs?: number;
  timeoutMs?: number;
} = {}): Promise<TagSyncStatus> {
  const {
    signal,
    intervalMs = CATEGORY_REFRESH_POLL_MS,
    timeoutMs = CATEGORY_REFRESH_TIMEOUT_MS,
  } = options;
  const deadline = Date.now() + timeoutMs;
  await abortableDelay(intervalMs, signal);
  for (;;) {
    const status = await fetchTagSyncStatus(signal);
    if (!status.category_refresh_running || Date.now() >= deadline) return status;
    await abortableDelay(intervalMs, signal);
    if (signal?.aborted) return status;
  }
}

export function syncGalleryTags(
  galleryId: number,
  signal?: AbortSignal,
): Promise<GalleryTagSyncResult> {
  return request<GalleryTagSyncResult>(
    { method: syncGalleryTagsEp.method, path: syncGalleryTagsEp.path.replace("{id}", String(galleryId)) },
    { signal },
  );
}
