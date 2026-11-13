/**
 * Local-library filter model (DESIGN.md C19, polish audit LB-02/LB-06).
 *
 * The page keeps one `LibraryFilters` object; every control patches it and the
 * URL is derived from it, so the query string and the visible state can never
 * drift apart. Nothing here touches the network or i18n: the view maps the
 * condition descriptors to translated chip labels, the store maps the object
 * to `GET /api/galleries` parameters.
 *
 * Size inputs stay in MB (as the legacy library form did) and are converted to
 * bytes only in `toGalleryQuery`. `page_size` is not a filter: it is carried in
 * the URL for deep links but never counted as an active condition.
 */
import { clampPageSize, type GalleryListQuery } from "@/stores/library";
import { libraryTagQuery, type TagLike } from "@/components/tags/tag-utils";

export interface LibraryFilters {
  term: string;
  tags: string;
  category: string;
  readStatus: string;
  orderBy: string;
  pageMin: string;
  pageMax: string;
  minRating: string;
  sizeMin: string;
  sizeMax: string;
  postedFrom: string;
  postedTo: string;
  uploader: string;
  imageQuality: string;
  minLocalRating: string;
  listId: string;
  pageSize: number;
}

export const DEFAULT_ORDER_BY = "id_desc";

export function defaultFilters(pageSize = 24): LibraryFilters {
  return {
    term: "",
    tags: "",
    category: "",
    readStatus: "",
    orderBy: DEFAULT_ORDER_BY,
    pageMin: "",
    pageMax: "",
    minRating: "",
    sizeMin: "",
    sizeMax: "",
    postedFrom: "",
    postedTo: "",
    uploader: "",
    imageQuality: "",
    minLocalRating: "",
    listId: "",
    pageSize,
  };
}

/** First value of a route query entry (arrays collapse to their first item). */
export function firstQuery(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

export function filtersFromQuery(
  query: Record<string, unknown>,
  fallbackPageSize = 24,
): LibraryFilters {
  return {
    term: firstQuery(query.q),
    tags: firstQuery(query.tags),
    category: firstQuery(query.category),
    readStatus: firstQuery(query.read_status),
    orderBy: firstQuery(query.order_by) || DEFAULT_ORDER_BY,
    // `min_pages` / `max_pages` are the legacy aliases kept for old bookmarks.
    pageMin: firstQuery(query.page_min) || firstQuery(query.min_pages),
    pageMax: firstQuery(query.page_max) || firstQuery(query.max_pages),
    minRating: firstQuery(query.min_rating),
    sizeMin: firstQuery(query.size_min),
    sizeMax: firstQuery(query.size_max),
    postedFrom: firstQuery(query.posted_from),
    postedTo: firstQuery(query.posted_to),
    uploader: firstQuery(query.uploader),
    imageQuality: firstQuery(query.image_quality),
    minLocalRating: firstQuery(query.min_local_rating),
    listId: firstQuery(query.list_id),
    pageSize: clampPageSize(firstQuery(query.page_size) || fallbackPageSize, fallbackPageSize),
  };
}

/**
 * Route query derived from the filters.
 *
 * `extra` carries parameters that are not filters but must survive a push
 * (`tag_mode`, `tag_match`); explicit filters win when both sides set a key.
 */
export function filtersToUrlQuery(
  filters: LibraryFilters,
  extra: Record<string, string> = {},
): Record<string, string> {
  const query: Record<string, string> = {};
  for (const [key, value] of Object.entries(extra)) {
    if (value) query[key] = value;
  }
  const set = (key: string, value: string): void => {
    if (value) query[key] = value;
    else delete query[key];
  };
  set("q", filters.term.trim());
  set("tags", filters.tags);
  set("category", filters.category);
  set("read_status", filters.readStatus);
  set("order_by", filters.orderBy || DEFAULT_ORDER_BY);
  set("min_rating", filters.minRating);
  set("page_min", filters.pageMin);
  set("page_max", filters.pageMax);
  set("size_min", filters.sizeMin);
  set("size_max", filters.sizeMax);
  set("posted_from", filters.postedFrom);
  set("posted_to", filters.postedTo);
  set("uploader", filters.uploader.trim());
  set("image_quality", filters.imageQuality);
  set("min_local_rating", filters.minLocalRating);
  set("list_id", filters.listId);
  query.page_size = String(filters.pageSize);
  return query;
}

function positiveInt(value: string): number | undefined {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : undefined;
}

function floatValue(value: string): number | undefined {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

/** Legacy size inputs are MB; the list endpoint expects bytes. */
function megabytes(value: string): number | undefined {
  const mb = floatValue(value);
  return mb === undefined ? undefined : Math.round(mb * 1048576);
}

/** `GET /api/galleries` parameters for the current filters. */
export function toGalleryQuery(filters: LibraryFilters): GalleryListQuery {
  return {
    q: filters.term.trim(),
    tags: filters.tags,
    category: filters.category,
    order_by: filters.orderBy || DEFAULT_ORDER_BY,
    read_status: filters.readStatus,
    min_rating: floatValue(filters.minRating),
    page_min: positiveInt(filters.pageMin),
    page_max: positiveInt(filters.pageMax),
    size_min: megabytes(filters.sizeMin),
    size_max: megabytes(filters.sizeMax),
    posted_from: filters.postedFrom,
    posted_to: filters.postedTo,
    uploader: filters.uploader.trim(),
    image_quality: filters.imageQuality,
    min_local_rating: positiveInt(filters.minLocalRating),
    list_id: positiveInt(filters.listId),
    page_size: filters.pageSize,
  };
}

export type FilterConditionKind =
  | "q"
  | "tag"
  | "category"
  | "read_status"
  | "page_min"
  | "page_max"
  | "min_rating"
  | "size_min"
  | "size_max"
  | "posted_from"
  | "posted_to"
  | "uploader"
  | "image_quality"
  | "min_local_rating"
  | "list_id";

export interface FilterCondition {
  kind: FilterConditionKind;
  /** Raw value from the filters (tag token, category key, number, date…). */
  value: string;
}

/** Comma separated `tags=` value split into trimmed, non-empty tokens. */
export function splitTagTokens(tags: string): string[] {
  return tags
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);
}

/**
 * Every active filter, in the same order the chip row renders them. Sorting and
 * the page size are deliberately absent: they are view settings, not conditions.
 */
export function activeConditions(filters: LibraryFilters): FilterCondition[] {
  const out: FilterCondition[] = [];
  const push = (kind: FilterConditionKind, value: string): void => {
    const trimmed = value.trim();
    if (trimmed) out.push({ kind, value: trimmed });
  };
  push("q", filters.term);
  for (const token of splitTagTokens(filters.tags)) {
    out.push({ kind: "tag", value: token });
  }
  push("category", filters.category);
  push("read_status", filters.readStatus);
  push("page_min", filters.pageMin);
  push("page_max", filters.pageMax);
  push("min_rating", filters.minRating);
  push("size_min", filters.sizeMin);
  push("size_max", filters.sizeMax);
  push("posted_from", filters.postedFrom);
  push("posted_to", filters.postedTo);
  push("uploader", filters.uploader);
  push("image_quality", filters.imageQuality);
  push("min_local_rating", filters.minLocalRating);
  push("list_id", filters.listId);
  return out;
}

/** FilterButton badge value: exactly the number of rendered condition chips. */
export function activeFilterCount(filters: LibraryFilters): number {
  return activeConditions(filters).length;
}

/**
 * True when a panel-only field is active. These are the filters that used to
 * sit behind "more filters"; the panel auto-opens for them after a deep link so
 * a bookmarked query is never silently applied (audit gaps: URL → visible state).
 */
export function hasAdvancedFilters(filters: LibraryFilters): boolean {
  return Boolean(
    filters.pageMin ||
      filters.pageMax ||
      filters.minRating ||
      filters.sizeMin ||
      filters.sizeMax ||
      filters.postedFrom ||
      filters.postedTo ||
      filters.uploader.trim() ||
      filters.imageQuality ||
      filters.minLocalRating ||
      filters.listId,
  );
}

/** Language filter currently expressed inside `tags=`. */
export function languageFromTags(tags: string): string {
  const hit = splitTagTokens(tags).find((token) => token.startsWith("language:"));
  return hit ? hit.slice("language:".length) : "";
}

/** Replace the single `language:*` token, keeping every other condition. */
export function withLanguageTag(tags: string, value: string): string {
  const rest = splitTagTokens(tags).filter(
    (token) => !token.startsWith("language:") && !token.startsWith("-language:"),
  );
  if (value) rest.push(`language:${value}`);
  return rest.join(",");
}

/** Remove one token from the comma separated filter (idempotent). */
export function removeTagToken(tags: string, token: string): string {
  return splitTagTokens(tags)
    .filter((entry) => entry !== token)
    .join(",");
}

/**
 * Append (or exclude) one tag on top of the current route query.
 *
 * Delegates to the shared idempotent helper so the library, favourites and
 * series pages produce the same `tags=` / `tag_mode=and` string.
 */
export function appendTagCondition(
  current: string | { tags?: unknown } | null | undefined,
  tag: TagLike,
  options: { exclude?: boolean } = {},
): { tags: string; tag_mode: "and" } {
  return libraryTagQuery(current, tag, options);
}

/** Parse a raw `namespace:name` token back into a chip label input. */
export function tagTokenToTag(token: string): TagLike {
  const raw = token.startsWith("-") ? token.slice(1) : token;
  const index = raw.indexOf(":");
  if (index <= 0) return { namespace: null, name: raw };
  return { namespace: raw.slice(0, index), name: raw.slice(index + 1) };
}
