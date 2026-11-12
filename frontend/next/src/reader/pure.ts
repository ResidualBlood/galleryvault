/**
 * Reader helpers that are independent of Vue and the DOM.
 *
 * They are the TypeScript port of `frontend/assets/views/reader.js`:
 * keyboard throttling, zoom clamping, failed-page cache, placeholder copy,
 * spread navigation and preload selection. Keeping them here lets the Vitest
 * suite cover the same behaviour the legacy node:test suite covered.
 */

export const READER_PAGE_FAILURE_TTL = 60_000;

export type ReaderMode = "ltr" | "rtl" | "double" | "double-rtl" | "webtoon";
export type ReaderFit = "height" | "width" | "original";

export const READER_MODES: readonly ReaderMode[] = [
  "ltr",
  "rtl",
  "double",
  "double-rtl",
  "webtoon",
];

export const READER_FITS: readonly ReaderFit[] = ["height", "width", "original"];

/** OS key-repeat is dropped; two deliberate presses closer than 80 ms collapse. */
export function shouldHandleReaderKey(
  now: number,
  last: number,
  repeat: boolean,
  threshold = 80,
): boolean {
  if (repeat) return false;
  if (!last) return true;
  return now - last >= threshold;
}

export function clampReaderScale(current: number, factor: number): number {
  return Math.min(3.5, Math.max(1, current * factor));
}

export function readerPageKey(galleryId: number | string, page: number): string {
  return `${galleryId}:${page}`;
}

export function markPageFailed(
  map: Map<string, number>,
  key: string,
  now = Date.now(),
): Map<string, number> {
  map.set(String(key), now);
  return map;
}

export function isPageFailed(
  map: Map<string, number>,
  key: string,
  now = Date.now(),
  ttl = READER_PAGE_FAILURE_TTL,
): boolean {
  const at = map.get(String(key));
  if (typeof at !== "number") return false;
  const age = now - at;
  return age >= 0 && age < ttl;
}

export type ReaderTranslate = (
  key: string,
  params?: Record<string, unknown>,
) => string;

/** 1-based placeholder copy; Vue escapes it when rendered. */
export function pagePlaceholderLabel(
  page: number,
  translate?: ReaderTranslate,
): string {
  const safe = Math.max(0, Number.parseInt(String(page), 10) || 0);
  const n = safe + 1;
  const fallback = `Page ${n} unavailable`;
  if (!translate) return fallback;
  const text = translate("pageUnavailable", { n });
  return text && text !== "pageUnavailable" ? text : fallback;
}

export interface ReaderNav {
  prevPage: number | null;
  nextPage: number | null;
  /** Normalised spread start (even pages snap to the previous odd page). */
  curPage: number;
  pages: number[];
}

export function isDoubleMode(mode: ReaderMode): boolean {
  return mode === "double" || mode === "double-rtl";
}

export function isRtlMode(mode: ReaderMode): boolean {
  return mode === "rtl" || mode === "double-rtl";
}

export function normalizeReaderPage(
  page: number,
  total: number,
  mode: ReaderMode,
): number {
  const safeTotal = Math.max(0, Math.floor(total));
  if (safeTotal === 0) return 0;
  const clamped = Math.min(Math.max(0, Math.floor(page)), safeTotal - 1);
  if (isDoubleMode(mode) && clamped > 0 && clamped % 2 === 0) {
    return clamped - 1;
  }
  return clamped;
}

/** Page 0 is a single cover; pages 1+ are spreads [1,2], [3,4], ... */
export function getReaderNav(
  page: number,
  total: number,
  mode: ReaderMode,
): ReaderNav {
  const safeTotal = Math.max(0, Math.floor(total));
  const curPage = normalizeReaderPage(page, safeTotal, mode);
  if (!isDoubleMode(mode)) {
    return {
      prevPage: curPage > 0 ? curPage - 1 : null,
      nextPage: curPage + 1 < safeTotal ? curPage + 1 : null,
      curPage,
      pages: safeTotal > 0 ? [curPage] : [],
    };
  }

  let prevPage: number | null = null;
  if (curPage === 1) prevPage = 0;
  else if (curPage > 1) prevPage = Math.max(1, curPage - 2);

  let nextPage: number | null = null;
  if (curPage === 0) nextPage = safeTotal > 1 ? 1 : null;
  else if (curPage + 2 < safeTotal) nextPage = curPage + 2;

  const pages = [curPage];
  if (curPage > 0 && curPage + 1 < safeTotal) pages.push(curPage + 1);
  return { prevPage, nextPage, curPage, pages };
}

/** Preload the next two pages (the legacy paged reader used three). */
export function selectPreloadPages(
  page: number,
  total: number,
  mode: ReaderMode,
  isFailed: (page: number) => boolean = () => false,
): number[] {
  const nav = getReaderNav(page, total, mode);
  const candidates = isDoubleMode(mode)
    ? nav.pages.length > 1
      ? [nav.curPage + 2, nav.curPage + 3]
      : [nav.curPage + 1, nav.curPage + 2]
    : [nav.curPage + 1, nav.curPage + 2];
  const seen = new Set<number>();
  const out: number[] = [];
  for (const index of candidates) {
    if (index < 0 || index >= total || seen.has(index)) continue;
    if (isFailed(index)) continue;
    seen.add(index);
    out.push(index);
  }
  return out.slice(0, 2);
}

/**
 * Estimated offsets for the vertical webtoon strip. `heights` are measured
 * pixel heights keyed by page; missing pages use `estimate`.
 */
export function buildWebtoonOffsets(
  total: number,
  heights: Record<number, number>,
  estimate: number,
): number[] {
  const offsets = new Array<number>(Math.max(0, total) + 1).fill(0);
  for (let i = 0; i < total; i += 1) {
    const height = heights[i];
    offsets[i + 1] = offsets[i] + (Number.isFinite(height) && height > 0 ? height : estimate);
  }
  return offsets;
}

export interface WebtoonWindow {
  start: number;
  end: number;
}

/**
 * Visible slice with overscan, hard-capped so a 500-page gallery never puts
 * hundreds of <img> nodes in the DOM.
 */
export function computeWebtoonWindow(
  offsets: number[],
  total: number,
  scrollTop: number,
  viewportHeight: number,
  overscan = 3,
  maxItems = 24,
): WebtoonWindow {
  if (total <= 0) return { start: 0, end: 0 };
  const top = Math.max(0, scrollTop);
  const bottom = top + Math.max(1, viewportHeight);
  let start = 0;
  while (start + 1 < total && offsets[start + 1] <= top) start += 1;
  let end = start + 1;
  while (end < total && offsets[end] < bottom) end += 1;
  start = Math.max(0, start - overscan);
  end = Math.min(total, end + overscan);
  if (end - start > maxItems) end = start + maxItems;
  return { start, end };
}

/** Which page owns the top third of the webtoon viewport. */
export function webtoonPageAt(
  offsets: number[],
  total: number,
  scrollTop: number,
  viewportHeight: number,
): number {
  if (total <= 0) return 0;
  const probe = scrollTop + viewportHeight * 0.34;
  let page = 0;
  while (page + 1 < total && offsets[page + 1] <= probe) page += 1;
  return page;
}
