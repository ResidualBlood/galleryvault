/**
 * Shared tag helpers for every surface that renders a tag.
 *
 * Rules (PLAN frontend-rewrite, polish phase §P6):
 * - the visible chip text is the tag body only; the namespace never becomes a
 *   prefix. `zh` uses the backend `display` translation (falling back to the
 *   raw name), every other locale uses the raw name;
 * - inline rows take the first N after a product priority and skip `language`
 *   (the language already has its own field);
 * - local library filtering appends to the comma-separated `tags=` filter and
 *   always pins `tag_mode=and`;
 * - online searching uses ExHentai's `ns:"name$"` exact syntax. Every helper
 *   is idempotent so repeated clicks cannot duplicate or double-quote a tag.
 */

export interface TagLike {
  namespace?: string | null;
  name: string;
  display?: string | null;
}

export type TagTranslator = (key: string) => string;

/** Payload of a long-press / context-menu request (viewport coordinates). */
export interface TagMenuEvent {
  tag: TagLike;
  x: number;
  y: number;
}

/** Inline priority from PLAN §P6; `language` is excluded separately. */
export const INLINE_NAMESPACE_ORDER = [
  "female",
  "male",
  "mixed",
  "character",
  "parody",
  "artist",
  "group",
  "cosplayer",
  "other",
] as const;

const INLINE_RANK = new Map<string, number>(
  INLINE_NAMESPACE_ORDER.map((namespace, index) => [namespace, index]),
);

/** Namespace used for tags whose namespace is missing or blank. */
export function tagNamespace(tag: Pick<TagLike, "namespace">): string {
  const value = typeof tag.namespace === "string" ? tag.namespace.trim() : "";
  return value || "misc";
}

/** Visible chip body: `display` in Chinese, raw name everywhere else. */
export function tagLabel(tag: TagLike, locale: string): string {
  const lang = (locale ?? "").toLowerCase();
  if (lang.startsWith("zh") && tag.display) return tag.display;
  return tag.name;
}

/** Raw `namespace:name` text used for copy, keys and tooltips. */
export function tagRawText(tag: TagLike): string {
  const namespace = typeof tag.namespace === "string" ? tag.namespace.trim() : "";
  return namespace ? `${namespace}:${tag.name}` : tag.name;
}

/** Stable de-duplication key for one tag. */
export function tagKey(tag: TagLike): string {
  const namespace = typeof tag.namespace === "string" ? tag.namespace.trim() : "";
  return namespace ? `${namespace}:${tag.name}` : tag.name;
}

/**
 * Localised namespace title (`gallery.namespaces.*`). Falls back to the raw
 * namespace so tooltips stay readable, but group rendering checks `te()`
 * separately and hides namespaces without a translation.
 */
export function namespaceLabel(namespace: string | null | undefined, t: TagTranslator): string {
  const value = typeof namespace === "string" ? namespace.trim() : "";
  const key = `gallery.namespaces.${value || "misc"}`;
  const translated = t(key);
  return translated && translated !== key ? translated : value || "misc";
}

function inlineRank(tag: TagLike): number {
  return INLINE_RANK.get(tagNamespace(tag)) ?? INLINE_NAMESPACE_ORDER.length;
}

/**
 * Order tags for an inline row and drop `language` tags. The sort is stable:
 * tags with the same rank keep their incoming order (the backend's order).
 */
export function sortTagsForInline<T extends TagLike>(tags: readonly T[]): T[] {
  return tags
    .filter((tag) => tagNamespace(tag) !== "language")
    .map((tag, index) => ({ tag, index, rank: inlineRank(tag) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((entry) => entry.tag);
}

export interface LibraryTagQuery {
  tags: string;
  tag_mode: "and";
}

export interface LibraryTagQueryOptions {
  exclude?: boolean;
}

function readCurrentTags(current: unknown): string {
  if (typeof current === "string") return current;
  if (!current || typeof current !== "object") return "";
  const value = (current as { tags?: unknown }).tags;
  if (Array.isArray(value)) return value.join(",");
  return typeof value === "string" ? value : "";
}

function splitFilterTokens(raw: string): string[] {
  return raw
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);
}

/**
 * Append (or exclude) one tag in the local library filter.
 *
 * Accepts either the existing `tags` string or the current route query. The
 * result always carries `tag_mode=and`; repeating the same action is
 * idempotent and flips an existing opposite token instead of duplicating it.
 */
export function libraryTagQuery(
  current: string | { tags?: unknown } | null | undefined,
  tag: TagLike,
  options: LibraryTagQueryOptions = {},
): LibraryTagQuery {
  const token = tagRawText(tag);
  const wanted = options.exclude ? `-${token}` : token;
  const opposite = options.exclude ? token : `-${token}`;
  const tokens = splitFilterTokens(readCurrentTags(current)).filter(
    (existing) => existing !== wanted && existing !== opposite,
  );
  tokens.push(wanted);
  return { tags: tokens.join(","), tag_mode: "and" };
}

/**
 * ExHentai exact tag search. `female` + `big breasts` becomes
 * `female:"big breasts$"`; values without whitespace keep the compact
 * `ns:name$` form. A value that already carries the namespace, quotes or the
 * trailing `$` produces the same normalized output again.
 */
export function formatEhTagQuery(
  namespace: string | null | undefined,
  name: string,
): string {
  const ns = typeof namespace === "string" ? namespace.trim() : "";
  let body = typeof name === "string" ? name.trim() : "";

  if (ns && body.toLowerCase().startsWith(`${ns.toLowerCase()}:`)) {
    body = body.slice(ns.length + 1).trim();
  }

  let quoted = false;
  if (body.length >= 2) {
    const first = body[0];
    const last = body[body.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      quoted = true;
      body = body.slice(1, -1).trim();
    }
  }

  if (body.endsWith("$")) body = body.slice(0, -1).trim();

  const needsQuote = quoted || /\s/.test(body);
  const wrapped = needsQuote ? `"${body}$"` : `${body}$`;
  return ns ? `${ns}:${wrapped}` : wrapped;
}
