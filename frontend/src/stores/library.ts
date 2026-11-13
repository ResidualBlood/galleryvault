import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
  fetchGalleries,
  type GalleryItem,
  type GalleryPage,
  type GalleryQuery,
} from "@/api/library";

export const DEFAULT_PAGE_SIZE = 24;
export const PAGE_SIZES: readonly number[] = [24, 50, 100, 200, 500];
export const MAX_INFINITE_ERRORS = 5;

/** Grid metrics come from DESIGN.md C02: min column 152px, 12px gutters. */
export const GRID_MIN_CARD_WIDTH = 152;
export const GRID_GAP = 12;
/** Cover (3:4) + two title lines + one meta line + padding, see GalleryCard. */
export const GRID_CARD_INFO_HEIGHT = 76;

/** Fixed row heights for the three collection views (DESIGN.md C18). */
export const LIST_ROW_HEIGHT = 152;
export const LIST_ROW_HEIGHT_COMPACT = 132;
export const TABLE_ROW_HEIGHT = 56;
/** Below this viewport the compact row heights and list-only fallback apply. */
export const COMPACT_VIEWPORT = 600;

/**
 * List query with the tag truncation override added by `be-list-tags`.
 *
 * `tags_limit: 0` returns every tag (the browse grid overlay and the list/tag
 * `+N` math need the full set); the backend keeps `4` as its default so older
 * callers are unchanged.
 */
export interface GalleryListQuery extends GalleryQuery {
  tags_limit?: number;
}

/** All query parameters understood by GET /api/galleries. */
const QUERY_KEYS = [
  "page",
  "page_size",
  "q",
  "category",
  "tags",
  "tag_mode",
  "tag_match",
  "order_by",
  "read_status",
  "min_rating",
  "page_min",
  "page_max",
  "size_min",
  "size_max",
  "posted_from",
  "posted_to",
  "uploader",
  "image_quality",
  "min_local_rating",
  "list_id",
  "tags_limit",
] as const;

export function clampPageSize(value: unknown, fallback = DEFAULT_PAGE_SIZE): number {
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.max(1, Math.min(500, Math.trunc(parsed)));
}

/**
 * Responsive column count for the virtual grid.
 *
 * `floor((width + gap) / (minWidth + gap))` keeps the resulting cards at or
 * above `minWidth`, matching CSS `repeat(auto-fill, minmax(152px, 1fr))`.
 */
export function computeColumnCount(
  containerWidth: number,
  minCardWidth = GRID_MIN_CARD_WIDTH,
  gap = GRID_GAP,
): number {
  if (!Number.isFinite(containerWidth) || containerWidth <= 0) return 1;
  const safeMin = Math.max(1, minCardWidth);
  const safeGap = Math.max(0, gap);
  return Math.max(1, Math.floor((containerWidth + safeGap) / (safeMin + safeGap)));
}

/** Width of one card (and therefore the cover height) inside the grid. */
export function computeColumnWidth(
  containerWidth: number,
  columns: number,
  gap = GRID_GAP,
): number {
  if (columns <= 0) return 0;
  return Math.max(0, (containerWidth - gap * (columns - 1)) / columns);
}

/** Estimated row height used by the windowing math (cover + info + gap). */
export function computeRowHeight(
  containerWidth: number,
  columns: number,
  gap = GRID_GAP,
): number {
  const width = computeColumnWidth(containerWidth, columns, gap);
  return Math.round(width * (4 / 3) + GRID_CARD_INFO_HEIGHT + gap);
}

/**
 * Height of one virtual row for a collection view.
 *
 * Grid rows grow with the column width (3:4 cover + 76px info + gutter), list
 * and table rows are fixed by token (see DESIGN.md C18); the compact list row
 * is the 132px token used below 600px.
 */
export function collectionRowHeight(
  mode: "grid" | "list" | "table",
  containerWidth: number,
  columns: number,
  gap = GRID_GAP,
  compact = false,
): number {
  if (mode === "list") return compact ? LIST_ROW_HEIGHT_COMPACT : LIST_ROW_HEIGHT;
  if (mode === "table") return TABLE_ROW_HEIGHT;
  return computeRowHeight(containerWidth, columns, gap);
}

/** Row index of the first partly visible row (0 when scrolled above). */
export function firstVisibleRow(scrollY: number, canvasTop: number, rowHeight: number): number {
  if (!Number.isFinite(rowHeight) || rowHeight <= 0) return 0;
  return Math.max(0, Math.floor(Math.max(0, scrollY - canvasTop) / rowHeight));
}

/** Item index of the first visible row, used as the view-switch anchor. */
export function firstVisibleItemIndex(
  scrollY: number,
  canvasTop: number,
  rowHeight: number,
  columns: number,
): number {
  const safeColumns = Math.max(1, Math.trunc(columns) || 1);
  return firstVisibleRow(scrollY, canvasTop, rowHeight) * safeColumns;
}

/** Scroll offset that puts `itemIndex` at the top of the viewport. */
export function scrollTopForItem(
  itemIndex: number,
  rowHeight: number,
  columns: number,
  canvasTop: number,
): number {
  const safeColumns = Math.max(1, Math.trunc(columns) || 1);
  const row = Math.floor(Math.max(0, itemIndex) / safeColumns);
  return Math.max(0, canvasTop + row * Math.max(0, rowHeight));
}

export function canAutoRetry(failures: number): boolean {
  return failures < MAX_INFINITE_ERRORS;
}

/** Keep only meaningful values; `page` is retained (the request needs it). */
export function normalizeQuery(
  input: GalleryListQuery,
  fallbackPageSize = DEFAULT_PAGE_SIZE,
): GalleryListQuery {
  const out: GalleryListQuery = {
    page_size: clampPageSize(input.page_size ?? fallbackPageSize),
  };
  for (const key of QUERY_KEYS) {
    if (key === "page_size") continue;
    const value = input[key];
    if (value === undefined || value === null || value === "") continue;
    if (key === "page") {
      const page = Number(value);
      if (Number.isFinite(page) && page >= 1) out.page = Math.trunc(page);
      continue;
    }
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (!trimmed) continue;
      (out as Record<string, unknown>)[key] = trimmed;
      continue;
    }
    (out as Record<string, unknown>)[key] = value;
  }
  return out;
}

/** Stable request parameters; empty strings/undefined are omitted. */
/**
 * Request parameters for one page.
 *
 * Every collection row needs the full tag list (the grid overlay, the list /
 * table `+N` counts and the tag filter all read from it), so the list request
 * always pins `tags_limit=0` unless the caller asked for another limit. This is
 * one local SQL read, not an EH request.
 */
export function withTagLimit(query: GalleryListQuery, page?: number): GalleryListQuery {
  return {
    ...query,
    ...(page !== undefined && page > 0 ? { page } : {}),
    tags_limit: query.tags_limit ?? 0,
  };
}

export function buildGalleryQuery(query: GalleryListQuery): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of QUERY_KEYS) {
    const value = (query as Record<string, unknown>)[key];
    if (value === undefined || value === null || value === "") continue;
    out[key] = String(value);
  }
  return out;
}

export function buildGalleryQueryString(query: GalleryListQuery): string {
  return new URLSearchParams(buildGalleryQuery(query)).toString();
}

/** Cache key: everything except the page number. */
export function queryCacheKey(query: GalleryListQuery): string {
  return buildGalleryQueryString({ ...query, page: undefined });
}

export function mergeUniqueById(existing: GalleryItem[], incoming: GalleryItem[]): GalleryItem[] {
  const seen = new Set(existing.map((item) => item.id));
  const merged = [...existing];
  for (const item of incoming) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push(item);
  }
  return merged;
}

export function progressPercent(current: number | null | undefined, total: number | null | undefined): number {
  const pages = Number(total) || 0;
  const page = Math.max(0, Number(current) || 0);
  if (pages <= 0) return 0;
  return Math.min(100, Math.round(((page + 1) / pages) * 100));
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes < 0) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

interface CacheEntry {
  items: GalleryItem[];
  page: number;
  total: number;
  exhausted: boolean;
  scrollY: number;
}

/** Survives component remounts (detail → back) within one SPA session. */
const listCache = new Map<string, CacheEntry>();

function toEntry(page: GalleryPage, items: GalleryItem[], exhausted: boolean, scrollY = 0): CacheEntry {
  return { items: [...items], page: page.page, total: page.total, exhausted, scrollY };
}

export const useLibraryStore = defineStore("library-list", () => {
  const items = ref<GalleryItem[]>([]);
  const page = ref(0);
  const total = ref(0);
  const pageSize = ref(DEFAULT_PAGE_SIZE);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const failures = ref(0);
  const exhausted = ref(false);
  const currentKey = ref("");
  const currentQuery = ref<GalleryListQuery>({});

  let controller: AbortController | null = null;
  let requestSeq = 0;

  const initialLoading = computed(() => loading.value && items.value.length === 0);
  const hasMore = computed(
    () => !exhausted.value && (total.value === 0 || items.value.length < total.value),
  );

  function remember(): void {
    if (!currentKey.value) return;
    const previous = listCache.get(currentKey.value);
    listCache.set(
      currentKey.value,
      toEntry(
        { total: total.value, page: page.value, page_size: pageSize.value, items: [] },
        items.value,
        exhausted.value,
        previous?.scrollY ?? 0,
      ),
    );
  }

  function reset(): void {
    requestSeq += 1;
    controller?.abort();
    controller = null;
    items.value = [];
    page.value = 0;
    total.value = 0;
    loading.value = false;
    error.value = null;
    failures.value = 0;
    exhausted.value = false;
  }

  async function loadPage(target: number): Promise<boolean> {
    const key = currentKey.value;
    if (!key) return false;
    const seq = ++requestSeq;
    controller?.abort();
    controller = new AbortController();
    loading.value = true;
    error.value = null;
    try {
      const data = await fetchGalleries(
        withTagLimit(currentQuery.value, target),
        controller.signal,
      );
      if (seq !== requestSeq || key !== currentKey.value) return false;
      page.value = data.page;
      total.value = data.total;
      items.value =
        target <= 1 ? data.items : mergeUniqueById(items.value, data.items);
      exhausted.value =
        data.items.length === 0 ||
        items.value.length >= data.total ||
        data.page * data.page_size >= data.total;
      failures.value = 0;
      remember();
      return true;
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return false;
      if (seq !== requestSeq) return false;
      error.value = caught instanceof Error ? caught.message : String(caught);
      failures.value += 1;
      return false;
    } finally {
      if (seq === requestSeq) loading.value = false;
    }
  }

  /**
   * Start (or resume) a list. Remounting after a detail visit reuses the cached
   * items and scroll offset, which is what the back-navigation contract needs.
   */
  function start(query: GalleryListQuery, fallbackPageSize = DEFAULT_PAGE_SIZE): void {
    const next = normalizeQuery(query, fallbackPageSize);
    const key = queryCacheKey(next);
    pageSize.value = next.page_size ?? fallbackPageSize;
    if (key === currentKey.value && (items.value.length > 0 || loading.value)) return;

    const cached = listCache.get(key);
    currentKey.value = key;
    currentQuery.value = next;
    error.value = null;
    failures.value = 0;
    if (cached) {
      items.value = [...cached.items];
      page.value = cached.page;
      total.value = cached.total;
      exhausted.value = cached.exhausted;
      loading.value = false;
      return;
    }
    reset();
    currentKey.value = key;
    currentQuery.value = next;
    void loadPage(1);
  }

  async function loadMore(): Promise<boolean> {
    if (loading.value || exhausted.value || !currentKey.value) return false;
    if (!canAutoRetry(failures.value)) return false;
    return loadPage(page.value + 1);
  }

  /**
   * Re-fetch the current page after a server-side mutation (batch delete).
   *
   * Unlike `loadPage` this always replaces the rows instead of appending, and
   * when the current page became empty it falls back to the new last page —
   * the same "delete the last row on page N" behavior as the legacy grid.
   */
  async function reload(): Promise<boolean> {
    const key = currentKey.value;
    if (!key) return false;
    const seq = ++requestSeq;
    controller?.abort();
    controller = new AbortController();
    loading.value = true;
    error.value = null;
    try {
      let target = Math.max(1, page.value || 1);
      let data = await fetchGalleries(
        withTagLimit(currentQuery.value, target),
        controller.signal,
      );
      if (seq !== requestSeq || key !== currentKey.value) return false;
      if (!data.items.length && data.total > 0 && target > 1) {
        const size = data.page_size || pageSize.value;
        const lastPage = Math.max(1, Math.ceil(data.total / Math.max(1, size)));
        if (lastPage !== target) {
          target = lastPage;
          data = await fetchGalleries(
            withTagLimit(currentQuery.value, target),
            controller.signal,
          );
          if (seq !== requestSeq || key !== currentKey.value) return false;
        }
      }
      page.value = data.page;
      total.value = data.total;
      items.value = data.items;
      exhausted.value =
        data.items.length === 0 ||
        items.value.length >= data.total ||
        data.page * data.page_size >= data.total;
      failures.value = 0;
      remember();
      return true;
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return false;
      if (seq !== requestSeq) return false;
      error.value = caught instanceof Error ? caught.message : String(caught);
      failures.value += 1;
      return false;
    } finally {
      if (seq === requestSeq) loading.value = false;
    }
  }

  /** Explicit "click to retry": resets the counter and retries the failed page. */
  async function retry(): Promise<boolean> {
    if (loading.value || !currentKey.value) return false;
    failures.value = 0;
    error.value = null;
    return loadPage(page.value + 1);
  }

  function saveScroll(scrollY: number): void {
    if (!currentKey.value) return;
    const cached = listCache.get(currentKey.value);
    if (cached) cached.scrollY = Math.max(0, scrollY);
  }

  function savedScroll(): number {
    return listCache.get(currentKey.value)?.scrollY ?? 0;
  }

  return {
    items,
    page,
    total,
    pageSize,
    loading,
    initialLoading,
    error,
    failures,
    exhausted,
    hasMore,
    currentKey,
    currentQuery,
    start,
    loadMore,
    retry,
    reload,
    saveScroll,
    savedScroll,
  };
});
