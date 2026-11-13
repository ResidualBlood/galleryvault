/**
 * Pure helpers for the online list page (PLAN polish §P6, DESIGN C03 / C18).
 *
 * Everything here is free of Vue / router state so unit tests can cover the
 * three rules the page depends on:
 *
 *   - the language of a row is inferred from its `language:*` tag (there is no
 *     separate backend field and no extra EH request);
 *   - clicking tags appends ExHentai's exact `ns:"name$"` token to the current
 *     query with a space (AND), idempotently;
 *   - the table columns are fixed (EH search cannot sort) and shrink by
 *     priority before the table ever scrolls horizontally.
 */
import {
  formatEhTagQuery,
  sortTagsForInline,
  tagLabel,
  tagNamespace,
  type TagLike,
} from "@/components/tags/tag-utils";
import type { TableColumn } from "@/components/gallery/table-columns";
import type { OnlineSearchItem } from "@/api/eh";

/** Split an EH query on whitespace, keeping quoted tag bodies intact. */
export function splitEhQuery(query: string | null | undefined): string[] {
  const text = typeof query === "string" ? query : "";
  const out: string[] = [];
  let buffer = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      quoted = !quoted;
      buffer += char;
      continue;
    }
    if (!quoted && /\s/.test(char)) {
      if (buffer.trim()) out.push(buffer.trim());
      buffer = "";
      continue;
    }
    buffer += char;
  }
  if (buffer.trim()) out.push(buffer.trim());
  return out;
}

/**
 * Append one tag to an online query. Repeated clicks return the same query
 * (idempotent), so a tag can never be duplicated in the search box.
 */
export function appendEhTagQuery(
  current: string | null | undefined,
  tag: TagLike,
): string {
  const token = formatEhTagQuery(tag.namespace, tag.name);
  const tokens = splitEhQuery(current);
  const normalized = token.toLowerCase();
  if (tokens.some((entry) => entry.toLowerCase() === normalized)) {
    return tokens.join(" ");
  }
  return [...tokens, token].join(" ");
}

/** First `language:*` tag, or null when the row has no language tag. */
export function languageTag(tags: readonly TagLike[] | null | undefined): TagLike | null {
  if (!Array.isArray(tags)) return null;
  return tags.find((tag) => tagNamespace(tag) === "language") ?? null;
}

/**
 * Localised language cell. `zh` uses the backend translation, every other
 * locale uses the raw tag name; a missing tag returns an empty string so the
 * meta line can omit the cell entirely.
 */
export function languageLabel(
  tags: readonly TagLike[] | null | undefined,
  locale: string,
): string {
  const tag = languageTag(tags);
  if (!tag) return "";
  return tagLabel(tag, locale);
}

/** Tags eligible for the inline row (language already has its own cell). */
export function inlineTags(tags: readonly TagLike[] | null | undefined): TagLike[] {
  if (!Array.isArray(tags)) return [];
  return sortTagsForInline(tags);
}

/**
 * Backend `posted` is a UTC epoch in seconds (be-st list parser). Format it as
 * ISO so every card uses the shared `formatDate`; unknown / epoch-0 is null.
 */
export function normalizePosted(
  value: string | number | null | undefined,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  let date: Date;
  if (typeof value === "number") {
    if (!Number.isFinite(value) || value <= 0) return null;
    date = new Date(value * 1000);
  } else if (/^\d+$/.test(value.trim())) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds <= 0) return null;
    date = new Date(seconds * 1000);
  } else {
    date = new Date(value);
  }
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() <= 1970) return null;
  return date.toISOString();
}

function column(key: string, labelKey: string, extra: Partial<TableColumn> = {}): TableColumn {
  return { key, labelKey, align: "start", priority: 50, ...extra };
}

/**
 * Online table columns (DESIGN C18): title / category / tags / pages / rating /
 * posted / status. No `sortKey` on purpose — EH search does not sort.
 */
export const ONLINE_TABLE_COLUMNS: readonly TableColumn[] = [
  column("selection", "select", { width: 40, align: "center", priority: 100 }),
  column("title", "title", {
    minWidth: 180,
    flex: 1,
    priority: 100,
    pinned: true,
  }),
  column("category", "category", { width: 96, hideBelow: 640, priority: 30 }),
  column("tags", "tags", { minWidth: 240, flex: 1, hideBelow: 720, priority: 20 }),
  column("pages", "pages", { width: 64, align: "end", priority: 70 }),
  column("rating", "rating", { width: 72, align: "end", hideBelow: 720, priority: 40 }),
  column("posted", "posted", { width: 100, align: "end", hideBelow: 900, priority: 20 }),
  column("status", "status", { width: 72, align: "center", hideBelow: 720, priority: 50 }),
];

/** Result of mapping one backend search item to the shared card model. */
export interface OnlineCardState {
  favorite: boolean;
  favorite_category: number | null;
  in_library: boolean;
  download_status: string | null;
}

/** Table rows do not render language; fold it out of the chip count too. */
export function withoutLanguageTags<T extends TagLike>(tags: readonly T[]): T[] {
  return tags.filter((tag) => tagNamespace(tag) !== "language");
}

/** True when the item carries enough info to render a real list row. */
export function hasSearchTags(item: OnlineSearchItem): boolean {
  return Array.isArray(item.tags) && item.tags.length > 0;
}
