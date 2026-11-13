import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
  ONLINE_LIST_TYPES,
  ONLINE_TOPLIST_VALUES,
  mapOnlineState,
  searchOnline,
  type OnlineListType,
  type OnlineSearchItem,
  type OnlineState,
} from "@/api/eh";

/** Legacy-compatible preference key (inv-frontend §3.5 rollback contract). */
export const ONLINE_DEFAULTS_KEY = "gv_online_defaults";

export const ONLINE_CATEGORIES = [
  "doujinshi",
  "manga",
  "artistcg",
  "gamecg",
  "western",
  "non-h",
  "image_set",
  "cosplay",
  "asianporn",
  "misc",
] as const;

export type OnlineCategory = (typeof ONLINE_CATEGORIES)[number];

/** ExHentai `f_cats` bits (backend `_EH_CAT_BITS`, legacy discover.js). */
export const ONLINE_CATEGORY_BITS: Record<OnlineCategory, number> = {
  doujinshi: 1,
  manga: 2,
  artistcg: 4,
  gamecg: 8,
  western: 16,
  "non-h": 32,
  image_set: 64,
  cosplay: 128,
  asianporn: 256,
  misc: 512,
};

export const ONLINE_CATEGORY_ALL = 1023;

export interface OnlineFilters {
  q: string;
  /** Disabled-category bitmask; 0 means every category is enabled. */
  category: number;
  min_rating: number | null;
  list: OnlineListType;
  tl: number;
}

export const DEFAULT_ONLINE_FILTERS: OnlineFilters = {
  q: "",
  category: 0,
  min_rating: null,
  list: "search",
  tl: 15,
};

export const FILTER_QUERY_KEYS = ["q", "category", "min_rating", "list", "tl"] as const;
type FilterKey = (typeof FILTER_QUERY_KEYS)[number];

function clampMask(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(ONLINE_CATEGORY_ALL, Math.trunc(parsed)));
}

function normalizeRating(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number.parseFloat(String(value));
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.max(0, Math.min(5, parsed));
}

function normalizeList(value: unknown): OnlineListType {
  const list = typeof value === "string" ? value.trim().toLowerCase() : "";
  return (ONLINE_LIST_TYPES as readonly string[]).includes(list)
    ? (list as OnlineListType)
    : "search";
}

function normalizeTl(value: unknown, list: OnlineListType): number {
  if (list !== "toplist") return 15;
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  return (ONLINE_TOPLIST_VALUES as readonly number[]).includes(parsed) ? parsed : 15;
}

/** Categories enabled for a disabled-bitmask (`mask` uses ExHentai `f_cats`). */
export function enabledCategories(mask: number): OnlineCategory[] {
  const safe = clampMask(mask);
  return ONLINE_CATEGORIES.filter((name) => (safe & ONLINE_CATEGORY_BITS[name]) === 0);
}

/**
 * Bitmask from the UI checkboxes.
 *
 * Mirrors legacy `discoverFCatsFromForm`: all-off and all-on both mean "no
 * filter" (0), because ExHentai treats `f_cats=0` as every category enabled.
 */
export function maskFromEnabled(names: readonly string[]): number {
  const enabled = new Set(names);
  const anyOn = ONLINE_CATEGORIES.some((name) => enabled.has(name));
  const allOn = ONLINE_CATEGORIES.every((name) => enabled.has(name));
  if (!anyOn || allOn) return 0;
  let disabled = 0;
  for (const name of ONLINE_CATEGORIES) {
    if (!enabled.has(name)) disabled |= ONLINE_CATEGORY_BITS[name];
  }
  return disabled;
}

export function toggleCategory(mask: number, name: OnlineCategory): number {
  const enabled = new Set(enabledCategories(mask));
  if (enabled.has(name)) enabled.delete(name);
  else enabled.add(name);
  return maskFromEnabled([...enabled]);
}

export function normalizeFilters(input: Partial<OnlineFilters> = {}): OnlineFilters {
  const list = normalizeList(input.list);
  return {
    q: typeof input.q === "string" ? input.q.trim() : "",
    category: clampMask(input.category),
    min_rating: normalizeRating(input.min_rating),
    list,
    tl: normalizeTl(input.tl, list),
  };
}

/** Read filters from a route query; absent keys are simply not returned. */
export function parseFiltersFromQuery(
  query: Record<string, unknown> | URLSearchParams,
): Partial<OnlineFilters> {
  const get = (key: FilterKey): unknown => {
    if (query instanceof URLSearchParams) return query.get(key) ?? undefined;
    const value = query[key];
    return Array.isArray(value) ? value[value.length - 1] : value;
  };
  const out: Partial<OnlineFilters> = {};
  const q = get("q");
  if (typeof q === "string") out.q = q;
  const category = get("category");
  if (category !== undefined && category !== null && category !== "") {
    out.category = clampMask(category);
  }
  const minRating = get("min_rating");
  if (minRating !== undefined && minRating !== null && minRating !== "") {
    out.min_rating = normalizeRating(minRating);
  }
  const list = get("list");
  if (typeof list === "string" && list) out.list = normalizeList(list);
  const tl = get("tl");
  if (tl !== undefined && tl !== null && tl !== "") {
    const parsed = Number.parseInt(String(tl), 10);
    if (Number.isFinite(parsed)) out.tl = parsed;
  }
  return out;
}

export function hasFilterQuery(query: Record<string, unknown> | URLSearchParams): boolean {
  return FILTER_QUERY_KEYS.some((key) => {
    if (query instanceof URLSearchParams) return query.has(key);
    return query[key] !== undefined && query[key] !== null && query[key] !== "";
  });
}

/** Omits values that are implied by the defaults, keeping URLs readable. */
export function filtersToQuery(filters: OnlineFilters): Record<string, string> {
  const normalized = normalizeFilters(filters);
  const out: Record<string, string> = {};
  if (normalized.q) out.q = normalized.q;
  if (normalized.category > 0) out.category = String(normalized.category);
  if (normalized.min_rating !== null) out.min_rating = String(normalized.min_rating);
  if (normalized.list !== "search") out.list = normalized.list;
  if (normalized.list === "toplist") out.tl = String(normalized.tl);
  return out;
}

export function filtersKey(filters: OnlineFilters): string {
  return JSON.stringify(normalizeFilters(filters));
}

function readDefaults(): OnlineFilters | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(ONLINE_DEFAULTS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<OnlineFilters> | null;
    if (!parsed || typeof parsed !== "object") return null;
    return normalizeFilters(parsed);
  } catch {
    return null;
  }
}

export function loadOnlineDefaults(): OnlineFilters {
  return readDefaults() ?? { ...DEFAULT_ONLINE_FILTERS };
}

export function saveOnlineDefaults(filters: OnlineFilters): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(ONLINE_DEFAULTS_KEY, JSON.stringify(normalizeFilters(filters)));
  } catch {
    /* storage may be blocked; the in-memory filters still drive this session */
  }
}

export function mergeDownloadBadge(
  status: string | null | undefined,
): { tone: "primary" | "neutral" | "error"; key: "downloading" | "queued" | "failed" } | null {
  switch ((status ?? "").toLowerCase()) {
    case "downloading":
      return { tone: "primary", key: "downloading" };
    case "pending":
    case "queued":
      return { tone: "neutral", key: "queued" };
    case "failed":
    case "error":
      return { tone: "error", key: "failed" };
    default:
      return null;
  }
}

export type OnlinePageDirection = "next" | "prev";

/** Replayable cursor state for one list page (URL query `next`/`prev`). */
export interface OnlineCursorState {
  cursor?: string | null;
  direction?: OnlinePageDirection;
  jump?: string | null;
  seek?: string | null;
}

interface CacheEntry {
  items: OnlineSearchItem[];
  state: OnlineState;
  nextCursor: string | null;
  prevCursor: string | null;
  cursor: string | null;
  direction: OnlinePageDirection;
  jump: string | null;
  seek: string | null;
  scrollY: number;
}

/** Survives list remounts (detail → back) for the whole SPA session. */
const listCache = new Map<string, CacheEntry>();

function mergeUnique(existing: OnlineSearchItem[], incoming: OnlineSearchItem[]): OnlineSearchItem[] {
  const seen = new Set(existing.map((item) => item.gid));
  const merged = [...existing];
  for (const item of incoming) {
    if (!item || seen.has(item.gid)) continue;
    seen.add(item.gid);
    merged.push(item);
  }
  return merged;
}

export const useOnlineStore = defineStore("online-list", () => {
  const items = ref<OnlineSearchItem[]>([]);
  const state = ref<OnlineState>("ok");
  const nextCursor = ref<string | null>(null);
  const prevCursor = ref<string | null>(null);
  const currentCursor = ref<string | null>(null);
  const currentDirection = ref<OnlinePageDirection>("next");
  const jump = ref<string | null>(null);
  const seek = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const currentKey = ref("");
  const currentFilters = ref<OnlineFilters>({ ...DEFAULT_ONLINE_FILTERS });

  let controller: AbortController | null = null;
  let requestSeq = 0;

  const initialLoading = computed(() => loading.value && items.value.length === 0);
  const hasMore = computed(() => Boolean(nextCursor.value) && !error.value);
  const hasPrev = computed(() => Boolean(prevCursor.value) && !error.value);

  function remember(): void {
    if (!currentKey.value) return;
    const previous = listCache.get(currentKey.value);
    listCache.set(currentKey.value, {
      items: [...items.value],
      state: state.value,
      nextCursor: nextCursor.value,
      prevCursor: prevCursor.value,
      cursor: currentCursor.value,
      direction: currentDirection.value,
      jump: jump.value,
      seek: seek.value,
      scrollY: previous?.scrollY ?? 0,
    });
  }

  interface LoadOptions {
    direction?: OnlinePageDirection;
    jump?: string | null;
    seek?: string | null;
  }

  async function load(
    cursor: string | null,
    append: boolean,
    options: LoadOptions = {},
  ): Promise<boolean> {
    const key = currentKey.value;
    if (!key) return false;
    const seq = ++requestSeq;
    controller?.abort();
    controller = new AbortController();
    loading.value = true;
    error.value = null;
    const direction = options.direction ?? "next";
    const jumpValue = options.jump ?? null;
    const seekValue = options.seek ?? null;
    try {
      const filters = currentFilters.value;
      const data = await searchOnline(
        {
          q: filters.q,
          category: filters.category,
          min_rating: filters.min_rating,
          list: filters.list,
          tl: filters.list === "toplist" ? filters.tl : null,
          next: direction === "next" ? cursor : null,
          prev: direction === "prev" ? cursor : null,
          jump: jumpValue,
          seek: seekValue,
        },
        controller.signal,
      );
      if (seq !== requestSeq || key !== currentKey.value) return false;

      const mapped = mapOnlineState(data.state);
      state.value =
        mapped === "ok" && data.items.length === 0 && !append ? "empty" : mapped;
      items.value = append ? mergeUnique(items.value, data.items) : data.items;
      nextCursor.value = mapped === "ok" ? data.next : null;
      prevCursor.value = mapped === "ok" ? (data.prev ?? null) : null;
      if (!append) {
        currentCursor.value = cursor;
        currentDirection.value = direction;
        jump.value = jumpValue;
        seek.value = seekValue;
      }
      remember();
      return true;
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return false;
      if (seq !== requestSeq) return false;
      error.value = caught instanceof Error ? caught.message : String(caught);
      return false;
    } finally {
      if (seq === requestSeq) loading.value = false;
    }
  }

  function emptyCursorState(): void {
    nextCursor.value = null;
    prevCursor.value = null;
    currentCursor.value = null;
    currentDirection.value = "next";
    jump.value = null;
    seek.value = null;
  }

  /**
   * Start or resume a filter set. Returns true when cached items were reused
   * (the list view then restores the previous scroll offset).
   *
   * `initial` replays a cursor from the URL query; when it differs from the
   * cached page the list refetches instead of showing stale rows.
   */
  function start(filters: OnlineFilters, initial: OnlineCursorState = {}): boolean {
    const normalized = normalizeFilters(filters);
    const key = filtersKey(normalized);
    const cursor = initial.cursor ?? null;
    const direction = initial.direction ?? "next";
    const jumpValue = initial.jump ?? null;
    const seekValue = initial.seek ?? null;
    const samePage =
      currentCursor.value === cursor &&
      currentDirection.value === direction &&
      jump.value === jumpValue &&
      seek.value === seekValue;
    currentFilters.value = normalized;
    if (
      key === currentKey.value &&
      samePage &&
      (items.value.length > 0 || loading.value)
    ) {
      return true;
    }

    const cached = listCache.get(key);
    currentKey.value = key;
    error.value = null;
    requestSeq += 1;
    controller?.abort();
    controller = null;
    if (
      cached &&
      cached.cursor === cursor &&
      cached.direction === direction &&
      cached.jump === jumpValue &&
      cached.seek === seekValue
    ) {
      items.value = [...cached.items];
      state.value = cached.state;
      nextCursor.value = cached.nextCursor;
      prevCursor.value = cached.prevCursor;
      currentCursor.value = cached.cursor;
      currentDirection.value = cached.direction;
      jump.value = cached.jump;
      seek.value = cached.seek;
      loading.value = false;
      return true;
    }
    items.value = [];
    state.value = "ok";
    emptyCursorState();
    void load(cursor, false, {
      direction,
      jump: jumpValue,
      seek: seekValue,
    });
    return false;
  }

  async function loadMore(): Promise<boolean> {
    if (loading.value || !nextCursor.value || !currentKey.value || error.value) return false;
    return load(nextCursor.value, true);
  }

  /** Replace the list with the next page (`next` cursor). */
  async function goNext(): Promise<boolean> {
    if (!nextCursor.value || !currentKey.value || error.value) return false;
    return load(nextCursor.value, false, { direction: "next" });
  }

  /** Replace the list with the previous page (`prev` cursor). */
  async function goPrev(): Promise<boolean> {
    if (!prevCursor.value || !currentKey.value || error.value) return false;
    const direction: OnlinePageDirection =
      currentFilters.value.list === "toplist" ? "next" : "prev";
    return load(prevCursor.value, false, { direction });
  }

  /** Toplist direct page jump: page 1 maps to no `p`, page N to `p=N-1`. */
  async function goToPage(page: number): Promise<boolean> {
    if (!currentKey.value || error.value) return false;
    if (currentFilters.value.list !== "toplist") return false;
    if (!Number.isInteger(page) || page < 1 || page > 200) return false;
    return load(page > 1 ? String(page - 1) : null, false, { direction: "next" });
  }

  /**
   * Date jump (`jump=1m` / `seek=YYYY-MM-DD`). E-Hentai extends an existing
   * cursor, so this requires the current page's next or prev cursor.
   */
  async function jumpDate(value: { jump?: string | null; seek?: string | null }): Promise<boolean> {
    if (!currentKey.value || error.value) return false;
    if (currentFilters.value.list === "toplist") return false;
    const jumpValue = value.jump ?? null;
    const seekValue = value.seek ?? null;
    if (Boolean(jumpValue) === Boolean(seekValue)) return false;
    const cursor = nextCursor.value ?? prevCursor.value;
    if (!cursor) return false;
    return load(cursor, false, {
      direction: nextCursor.value ? "next" : "prev",
      jump: jumpValue,
      seek: seekValue,
    });
  }

  async function retry(): Promise<boolean> {
    if (loading.value || !currentKey.value) return false;
    error.value = null;
    return load(currentCursor.value, false, {
      direction: currentDirection.value,
      jump: jump.value,
      seek: seek.value,
    });
  }

  function saveScroll(scrollY: number): void {
    if (!currentKey.value) return;
    const cached = listCache.get(currentKey.value);
    if (cached) cached.scrollY = Math.max(0, scrollY);
    else {
      listCache.set(currentKey.value, {
        items: [...items.value],
        state: state.value,
        nextCursor: nextCursor.value,
        prevCursor: prevCursor.value,
        cursor: currentCursor.value,
        direction: currentDirection.value,
        jump: jump.value,
        seek: seek.value,
        scrollY: Math.max(0, scrollY),
      });
    }
  }

  function savedScroll(): number {
    return listCache.get(currentKey.value)?.scrollY ?? 0;
  }

  function clearCache(): void {
    listCache.clear();
  }

  return {
    items,
    state,
    nextCursor,
    prevCursor,
    currentCursor,
    currentDirection,
    jump,
    seek,
    loading,
    initialLoading,
    error,
    hasMore,
    hasPrev,
    currentKey,
    currentFilters,
    start,
    loadMore,
    goNext,
    goPrev,
    goToPage,
    jumpDate,
    retry,
    saveScroll,
    savedScroll,
    clearCache,
  };
});
