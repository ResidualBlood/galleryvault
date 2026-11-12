/**
 * Single query constructor for `GET /api/favorites/{favcat}/items`.
 *
 * The legacy view built the same 15 filters three times (view, pager, infinite
 * scroll), which made every new filter three edits. Everything now goes through
 * `buildFavListParams`; the unit test asserts the full 15-parameter surface.
 */

export const FAV_LIST_FILTER_KEYS = [
  "q",
  "category",
  "order_by",
  "read_status",
  "page_min",
  "page_max",
  "min_rating",
  "size_min",
  "size_max",
  "posted_from",
  "posted_to",
  "uploader",
  "image_quality",
  "language",
  "min_local_rating",
] as const;

export type FavListFilterKey = (typeof FAV_LIST_FILTER_KEYS)[number];

export const DEFAULT_FAV_ORDER = "last_seen_desc";

export interface FavListFilters extends Record<FavListFilterKey, string> {
  state: "all" | "local" | "cloud";
  page: number;
  page_size: number;
  tag_mode: "and" | "or";
  tag_match: "exact" | "fuzzy";
  /** Extra tags (not one of the 15 first-class filters). */
  tags: string;
  exclude_tags: string;
}

export function emptyFavListFilters(pageSize = 24): FavListFilters {
  return {
    q: "",
    category: "",
    order_by: DEFAULT_FAV_ORDER,
    read_status: "",
    page_min: "",
    page_max: "",
    min_rating: "",
    size_min: "",
    size_max: "",
    posted_from: "",
    posted_to: "",
    uploader: "",
    image_quality: "",
    language: "",
    min_local_rating: "",
    state: "all",
    page: 1,
    page_size: pageSize,
    tag_mode: "and",
    tag_match: "exact",
    tags: "",
    exclude_tags: "",
  };
}

function first(value: unknown): string {
  if (Array.isArray(value)) return first(value[0]);
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = typeof value === "number" ? value : Number.parseInt(first(value), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, Math.trunc(parsed)));
}

function splitTags(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** Merge the language select into `tags` (the backend has no language param). */
export function tagsWithLanguage(tags: string, language: string): string {
  const kept = splitTags(tags).filter((tag) => !tag.toLowerCase().startsWith("language:"));
  const normalizedLanguage = language.trim().toLowerCase();
  if (normalizedLanguage) kept.push(`language:${normalizedLanguage}`);
  return kept.join(",");
}

/** The decimal number in the size inputs is MiB; the backend expects bytes. */
export function megabytesToBytes(value: string): string {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0) return "";
  return String(Math.round(parsed * 1_048_576));
}

export function buildFavListParams(filters: FavListFilters): URLSearchParams {
  const params = new URLSearchParams();
  params.set("page", String(Math.max(1, Math.trunc(filters.page) || 1)));
  params.set(
    "page_size",
    String(Math.max(1, Math.min(500, Math.trunc(filters.page_size) || 24))),
  );
  params.set("state", filters.state);

  const q = filters.q.trim();
  if (q) params.set("q", q);
  if (filters.category) params.set("category", filters.category);
  if (filters.order_by && filters.order_by !== DEFAULT_FAV_ORDER) {
    params.set("order_by", filters.order_by);
  }
  if (filters.read_status) params.set("read_status", filters.read_status);

  const tags = tagsWithLanguage(filters.tags, filters.language);
  if (tags) {
    params.set("tags", tags);
    params.set("tag_mode", filters.tag_mode);
    if (filters.tag_match !== "exact") params.set("tag_match", filters.tag_match);
  }
  if (filters.exclude_tags.trim()) params.set("exclude_tags", filters.exclude_tags.trim());

  if (filters.page_min) {
    const value = Number.parseInt(filters.page_min, 10);
    if (Number.isFinite(value) && value > 0) params.set("page_min", String(value));
  }
  if (filters.page_max) {
    const value = Number.parseInt(filters.page_max, 10);
    if (Number.isFinite(value) && value > 0) params.set("page_max", String(value));
  }
  if (filters.min_rating) {
    const rating = Number.parseFloat(filters.min_rating);
    if (Number.isFinite(rating)) params.set("min_rating", String(rating));
  }
  if (filters.size_min) {
    const bytes = megabytesToBytes(filters.size_min);
    if (bytes) params.set("size_min", bytes);
  }
  if (filters.size_max) {
    const bytes = megabytesToBytes(filters.size_max);
    if (bytes) params.set("size_max", bytes);
  }
  if (filters.posted_from) params.set("posted_from", filters.posted_from);
  if (filters.posted_to) params.set("posted_to", filters.posted_to);
  if (filters.uploader.trim()) params.set("uploader", filters.uploader.trim());
  if (filters.image_quality) params.set("image_quality", filters.image_quality);
  if (filters.min_local_rating) {
    const rating = clampInt(filters.min_local_rating, 0, 1, 5);
    if (rating) params.set("min_local_rating", String(rating));
  }

  return params;
}

/** Router query -> filters; unknown keys are ignored, sizes stay in MiB. */
export function filtersFromQuery(
  query: Record<string, unknown>,
  pageSize = 24,
): FavListFilters {
  const filters = emptyFavListFilters(pageSize);
  filters.q = first(query.q);
  filters.category = first(query.category);
  filters.order_by = first(query.order_by) || DEFAULT_FAV_ORDER;
  filters.read_status = first(query.read_status);
  filters.page_min = first(query.page_min) || first(query.min_pages);
  filters.page_max = first(query.page_max) || first(query.max_pages);
  filters.min_rating = first(query.min_rating);
  filters.size_min = first(query.size_min);
  filters.size_max = first(query.size_max);
  filters.posted_from = first(query.posted_from);
  filters.posted_to = first(query.posted_to);
  filters.uploader = first(query.uploader);
  filters.image_quality = first(query.image_quality);
  filters.min_local_rating = first(query.min_local_rating);

  const tags = first(query.tags);
  filters.tags = tags;
  const languageTag = splitTags(tags).find((tag) =>
    tag.toLowerCase().startsWith("language:"),
  );
  filters.language = first(query.language) || (languageTag ? languageTag.split(":")[1] ?? "" : "");
  filters.exclude_tags = first(query.exclude_tags);
  filters.tag_mode = first(query.tag_mode) === "or" ? "or" : "and";
  filters.tag_match = first(query.tag_match) === "fuzzy" ? "fuzzy" : "exact";

  const state = first(query.state);
  filters.state = state === "local" || state === "cloud" ? state : "all";
  filters.page = clampInt(query.page, 1, 1, 100_000);
  filters.page_size = clampInt(query.page_size, pageSize, 1, 500);
  return filters;
}

export function activeFavFilterCount(filters: FavListFilters): number {
  return FAV_LIST_FILTER_KEYS.filter((key) => {
    if (key === "order_by") return filters.order_by !== DEFAULT_FAV_ORDER;
    return filters[key].trim() !== "";
  }).length;
}

/**
 * Router query: user-facing values (size inputs stay in MiB, language stays a
 * separate select), so `filtersFromQuery` round-trips without multiplying sizes.
 * Use `buildFavListParams` for the actual API call.
 */
export function favListQuery(filters: FavListFilters): Record<string, string> {
  const out: Record<string, string> = {
    state: filters.state,
    page: String(Math.max(1, Math.trunc(filters.page) || 1)),
    page_size: String(Math.max(1, Math.min(500, Math.trunc(filters.page_size) || 24))),
  };
  for (const key of FAV_LIST_FILTER_KEYS) {
    const value = filters[key].trim();
    if (!value) continue;
    if (key === "order_by" && value === DEFAULT_FAV_ORDER) continue;
    out[key] = value;
  }
  if (filters.tags.trim()) {
    out.tags = filters.tags.trim();
    out.tag_mode = filters.tag_mode;
    if (filters.tag_match !== "exact") out.tag_match = filters.tag_match;
  }
  if (filters.exclude_tags.trim()) out.exclude_tags = filters.exclude_tags.trim();
  return out;
}
