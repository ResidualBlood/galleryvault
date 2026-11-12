import { reactive, ref } from "vue";
import { defineStore } from "pinia";
import { fetchOnlineStatus } from "@/api/eh";
import {
  createDownload,
  fetchDownloads,
  type DownloadQuality,
  type DownloadTask,
} from "@/api/downloads";

/** PLAN §4.1: 2s while a visible tab has queued/downloading work, 10s idle. */
export const DOWNLOAD_ACTIVE_POLL_MS = 2000;
export const DOWNLOAD_IDLE_POLL_MS = 10000;
export const DOWNLOAD_PROGRESS_PAGE_SIZE = 500;

/** Per-device quick-download quality; the backend default is used on first run. */
export const DOWNLOAD_QUALITY_KEY = "gv_download_quality";

export type DownloadPhase = "idle" | "queued" | "downloading" | "success" | "failed";

export interface DownloadEntry {
  status: DownloadPhase;
  currentPage: number;
  totalPages: number | null;
  taskId: number | null;
  inLibrary: boolean;
  error: string | null;
  pending: boolean;
}

export interface DownloadSeed {
  status?: string | null;
  currentPage?: number | null;
  totalPages?: number | null;
  inLibrary?: boolean;
}

export function normalizeQuality(value: unknown): DownloadQuality {
  return value === "original" ? "original" : "resample";
}

export function readDefaultQuality(): DownloadQuality {
  try {
    return normalizeQuality(localStorage.getItem(DOWNLOAD_QUALITY_KEY));
  } catch {
    return "resample";
  }
}

export function rememberDefaultQuality(quality: DownloadQuality): DownloadQuality {
  const normalized = normalizeQuality(quality);
  try {
    localStorage.setItem(DOWNLOAD_QUALITY_KEY, normalized);
  } catch {
    /* storage may be blocked; the choice still applies to this click */
  }
  return normalized;
}

export function mapDownloadStatus(raw: unknown): DownloadPhase {
  switch (typeof raw === "string" ? raw.trim().toLowerCase() : "") {
    case "pending":
    case "queued":
      return "queued";
    case "downloading":
    case "running":
      return "downloading";
    case "success":
    case "completed":
      return "success";
    case "failed":
    case "error":
      return "failed";
    default:
      return "idle";
  }
}

function emptyEntry(): DownloadEntry {
  return {
    status: "idle",
    currentPage: 0,
    totalPages: null,
    taskId: null,
    inLibrary: false,
    error: null,
    pending: false,
  };
}

function isActiveStatus(status: DownloadPhase): boolean {
  return status === "queued" || status === "downloading";
}

/**
 * Global download state for cards / detail / reader badges.
 *
 * Badge state is keyed by gid and refreshed in batches with
 * `GET /api/eh/status` (100 gids per call). Page progress (`x/y`) comes from
 * `GET /api/downloads?status=downloading`; the backend accepts a single status
 * value per request (verified in `db/repositories/downloads.py:list_page`).
 *
 * Poll cadence follows visibility: hidden tabs pause entirely, visible tabs
 * poll every 2s while any watched gid is queued/downloading and every 10s
 * otherwise. Failed requests never stop the scheduler.
 */
export const useDownloadsStore = defineStore("downloads", () => {
  const entries = reactive<Record<number, DownloadEntry>>({});
  const watched = ref<number[]>([]);
  const watchCounts = new Map<number, number>();
  const polling = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let refreshPromise: Promise<void> | null = null;
  let refreshSoonScheduled = false;
  let listenerBound = false;

  function ensure(gid: number, seed?: DownloadSeed): DownloadEntry {
    if (!entries[gid]) {
      entries[gid] = emptyEntry();
      if (seed) applySeed(gid, seed);
    }
    return entries[gid];
  }

  function applySeed(gid: number, seed: DownloadSeed): void {
    const entry = ensure(gid);
    const mapped = mapDownloadStatus(seed.status);
    if (mapped !== "idle" || entry.status === "idle") entry.status = mapped;
    if (typeof seed.currentPage === "number") entry.currentPage = Math.max(0, seed.currentPage);
    if (seed.totalPages === null || typeof seed.totalPages === "number") {
      entry.totalPages = seed.totalPages;
    }
    if (seed.inLibrary) {
      entry.inLibrary = true;
      if (entry.status === "idle") entry.status = "success";
    }
  }

  function get(gid: number): DownloadEntry {
    return entries[gid] ?? ensure(gid);
  }

  function isHidden(): boolean {
    return typeof document !== "undefined" && document.visibilityState === "hidden";
  }

  function hasActive(): boolean {
    return watched.value.some((gid) => isActiveStatus(entries[gid]?.status ?? "idle"));
  }

  function nextInterval(): number {
    return hasActive() ? DOWNLOAD_ACTIVE_POLL_MS : DOWNLOAD_IDLE_POLL_MS;
  }

  function clearTimer(): void {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function schedule(delay = nextInterval()): void {
    clearTimer();
    if (isHidden() || watched.value.length === 0) return;
    timer = setTimeout(() => {
      timer = null;
      void tick();
    }, delay);
  }

  function onVisibility(): void {
    if (isHidden()) {
      clearTimer();
      polling.value = false;
      return;
    }
    if (watched.value.length) {
      void tick();
    }
  }

  function bindVisibility(): void {
    if (listenerBound || typeof document === "undefined") return;
    document.addEventListener("visibilitychange", onVisibility);
    listenerBound = true;
  }

  function unbindVisibility(): void {
    if (!listenerBound || typeof document === "undefined") return;
    document.removeEventListener("visibilitychange", onVisibility);
    listenerBound = false;
  }

  function mergeProgress(tasks: DownloadTask[]): void {
    const wanted = new Set(watched.value);
    for (const task of tasks) {
      if (!wanted.has(task.gid)) continue;
      const entry = ensure(task.gid);
      entry.taskId = task.id || entry.taskId;
      const mapped = mapDownloadStatus(task.status);
      if (mapped !== "idle") entry.status = mapped;
      entry.currentPage = Math.max(0, Number(task.current_page) || 0);
      entry.totalPages =
        typeof task.total_pages === "number" ? Math.max(0, task.total_pages) : entry.totalPages;
    }
  }

  async function doRefresh(): Promise<void> {
    if (isHidden() || watched.value.length === 0) return;
    const gids = [...watched.value];
    const items = await fetchOnlineStatus(gids);
    const byGid = new Map(items.map((item) => [item.gid, item]));
    for (const gid of gids) {
      const item = byGid.get(gid);
      if (!item) continue;
      const entry = ensure(gid);
      if (item.in_library) {
        entry.inLibrary = true;
        entry.status = "success";
        entry.currentPage = entry.totalPages ?? entry.currentPage;
      } else {
        const mapped = mapDownloadStatus(item.download_status);
        if (mapped !== "idle") {
          entry.status = mapped;
        } else if (!isActiveStatus(entry.status)) {
          entry.status = "idle";
        }
      }
    }

    const downloading = watched.value.filter((gid) => entries[gid]?.status === "downloading");
    if (downloading.length) {
      const page = await fetchDownloads({
        status: "downloading",
        page_size: DOWNLOAD_PROGRESS_PAGE_SIZE,
      });
      mergeProgress(page.items);
    }
  }

  function refresh(): Promise<void> {
    if (refreshPromise) return refreshPromise;
    refreshPromise = doRefresh()
      .catch(() => {
        /* polling is best-effort; the next tick retries */
      })
      .finally(() => {
        refreshPromise = null;
      });
    return refreshPromise;
  }

  /**
   * Coalesce the refreshes triggered while a grid mounts: all watches in the
   * same task produce one batched `/api/eh/status` request.
   */
  function refreshSoon(): void {
    if (refreshSoonScheduled) return;
    refreshSoonScheduled = true;
    queueMicrotask(() => {
      refreshSoonScheduled = false;
      if (isHidden() || watched.value.length === 0) return;
      void refresh().finally(() => {
        if (timer === null && !isHidden() && watched.value.length) schedule();
      });
    });
  }

  async function tick(): Promise<void> {
    if (isHidden() || watched.value.length === 0) return;
    polling.value = true;
    try {
      await refresh();
    } finally {
      polling.value = false;
      schedule();
    }
  }

  function watch(gid: number, seed?: DownloadSeed): void {
    ensure(gid, seed);
    const count = watchCounts.get(gid) ?? 0;
    watchCounts.set(gid, count + 1);
    const added = !watched.value.includes(gid);
    if (added) watched.value = [...watched.value, gid];
    bindVisibility();
    if (!isHidden()) {
      if (added) refreshSoon();
      else if (timer === null) schedule();
    }
  }

  function unwatch(gid: number): void {
    const count = watchCounts.get(gid) ?? 0;
    if (count > 1) {
      watchCounts.set(gid, count - 1);
      return;
    }
    watchCounts.delete(gid);
    watched.value = watched.value.filter((value) => value !== gid);
    if (!watched.value.length) {
      clearTimer();
      polling.value = false;
    }
  }

  async function enqueue(
    gid: number,
    token: string,
    options: { title?: string; quality?: DownloadQuality } = {},
  ): Promise<boolean> {
    const entry = ensure(gid);
    if (entry.pending || isActiveStatus(entry.status)) return false;
    entry.pending = true;
    entry.error = null;
    try {
      const result = await createDownload({
        gid,
        token,
        title: options.title,
        quality: options.quality ?? readDefaultQuality(),
      });
      entry.taskId = result.id || entry.taskId;
      entry.status = "queued";
      entry.error = null;
      watch(gid);
      return true;
    } catch (error) {
      const status = (error as { status?: number }).status;
      if (status === 409) {
        entry.status = "queued";
        watch(gid);
        return true;
      }
      entry.status = "failed";
      entry.error = error instanceof Error ? error.message : "download failed";
      throw error;
    } finally {
      entry.pending = false;
    }
  }

  function stop(): void {
    clearTimer();
    unbindVisibility();
    polling.value = false;
  }

  return {
    entries,
    watched,
    polling,
    ensure,
    applySeed,
    get,
    hasActive,
    nextInterval,
    refresh,
    tick,
    watch,
    unwatch,
    enqueue,
    stop,
  };
});

export type { DownloadQuality } from "@/api/downloads";
