import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  READER_PAGE_FAILURE_TTL,
  buildWebtoonOffsets,
  clampReaderScale,
  computeWebtoonWindow,
  getReaderNav,
  isPageFailed,
  markPageFailed,
  normalizeReaderPage,
  pagePlaceholderLabel,
  readerPageKey,
  selectPreloadPages,
  shouldHandleReaderKey,
  webtoonPageAt,
} from "./pure";
import {
  READER_FIT_KEY,
  READER_MODE_KEY,
  SLIDESHOW_INTERVAL_KEY,
  readReaderFit,
  readReaderMode,
  readSlideshowInterval,
  writeReaderFit,
  writeReaderMode,
  writeSlideshowInterval,
} from "./storage";
import { ProgressWriter } from "./progress";
import { LocalPageSource } from "./local-source";
import { readerPagePath } from "@/api/reader";

describe("keyboard throttling", () => {
  it("drops OS key repeat", () => {
    expect(shouldHandleReaderKey(1000, 0, true, 80)).toBe(false);
    expect(shouldHandleReaderKey(5000, 1000, true, 80)).toBe(false);
  });

  it("always handles the first press", () => {
    expect(shouldHandleReaderKey(1000, 0, false, 80)).toBe(true);
  });

  it("keeps 100ms deliberate taps instead of swallowing them", () => {
    expect(shouldHandleReaderKey(1100, 1000, false, 80)).toBe(true);
    expect(shouldHandleReaderKey(1000, 960, false, 80)).toBe(false);
    expect(shouldHandleReaderKey(1000, 920, false, 80)).toBe(true);
    expect(shouldHandleReaderKey(1000, 950, false)).toBe(false);
    expect(shouldHandleReaderKey(1000, 920, false)).toBe(true);
  });
});

describe("zoom", () => {
  it("clamps to 1x–3.5x", () => {
    expect(clampReaderScale(1, 1.5)).toBe(1.5);
    expect(clampReaderScale(2, 2)).toBe(3.5);
    expect(clampReaderScale(2, 0.1)).toBe(1);
    expect(clampReaderScale(3.5, 1.2)).toBe(3.5);
  });
});

describe("failed page cache", () => {
  it("hits within the TTL and retries afterwards", () => {
    const map = new Map<string, number>();
    markPageFailed(map, readerPageKey(12, 3), 1000);
    expect(isPageFailed(map, "12:3", 1000, 60_000)).toBe(true);
    expect(isPageFailed(map, "12:3", 60_999, 60_000)).toBe(true);
    expect(isPageFailed(map, "12:3", 61_000, 60_000)).toBe(false);
    expect(isPageFailed(map, "12:3", 500, 60_000)).toBe(false);
    expect(isPageFailed(map, "12:4", 1001, 60_000)).toBe(false);
    expect(READER_PAGE_FAILURE_TTL).toBe(60_000);
  });

  it("keeps galleries apart", () => {
    const map = new Map<string, number>();
    markPageFailed(map, readerPageKey(12, 3), 1000);
    expect(isPageFailed(map, "12:3", 1001)).toBe(true);
    expect(isPageFailed(map, "13:3", 1001)).toBe(false);
    expect(readerPageKey(12, 3)).toBe(readerPageKey("12", 3));
    expect(readerPageKey("12", 3)).toBe("12:3");
  });
});

describe("placeholder copy", () => {
  it("is 1-based and accepts a translator", () => {
    expect(pagePlaceholderLabel(4)).toBe("Page 5 unavailable");
    expect(
      pagePlaceholderLabel(4, (key, params) =>
        key === "pageUnavailable" ? `第 ${params?.n} 页不可用` : key,
      ),
    ).toBe("第 5 页不可用");
  });

  it("falls back when the translator does not know the key", () => {
    expect(pagePlaceholderLabel(0, (key) => key)).toBe("Page 1 unavailable");
  });
});

describe("spread navigation", () => {
  it("treats page 0 as a single cover", () => {
    expect(getReaderNav(0, 10, "double")).toEqual({
      prevPage: null,
      nextPage: 1,
      curPage: 0,
      pages: [0],
    });
  });

  it("pairs pages 1+ into [1,2], [3,4]", () => {
    expect(getReaderNav(1, 10, "double")).toEqual({
      prevPage: 0,
      nextPage: 3,
      curPage: 1,
      pages: [1, 2],
    });
    expect(getReaderNav(3, 10, "double")).toEqual({
      prevPage: 1,
      nextPage: 5,
      curPage: 3,
      pages: [3, 4],
    });
    expect(getReaderNav(8, 10, "double").pages).toEqual([7, 8]);
    expect(getReaderNav(7, 10, "double").pages).toEqual([7, 8]);
    expect(getReaderNav(9, 10, "double").nextPage).toBeNull();
  });

  it("normalises even pages to the spread start", () => {
    expect(normalizeReaderPage(4, 10, "double")).toBe(3);
    expect(normalizeReaderPage(0, 10, "double")).toBe(0);
    expect(normalizeReaderPage(4, 10, "ltr")).toBe(4);
  });

  it("moves one page at a time in single modes", () => {
    expect(getReaderNav(3, 10, "rtl")).toMatchObject({ prevPage: 2, nextPage: 4 });
    expect(getReaderNav(9, 10, "ltr").nextPage).toBeNull();
  });
});

describe("preload selection", () => {
  it("skips failed pages and caps at two", () => {
    expect(selectPreloadPages(2, 10, "ltr")).toEqual([3, 4]);
    expect(selectPreloadPages(2, 10, "ltr", (page) => page === 3)).toEqual([4]);
    expect(selectPreloadPages(8, 10, "ltr")).toEqual([9]);
    expect(selectPreloadPages(0, 10, "double")).toEqual([1, 2]);
  });
});

describe("webtoon virtualisation", () => {
  it("builds offsets from measured heights and estimates", () => {
    const offsets = buildWebtoonOffsets(3, { 0: 100, 2: 300 }, 200);
    expect(offsets).toEqual([0, 100, 300, 600]);
  });

  it("keeps the rendered slice small for 500 pages", () => {
    const total = 500;
    const offsets = buildWebtoonOffsets(total, {}, 900);
    const win = computeWebtoonWindow(offsets, total, 9_000, 900, 4, 22);
    expect(win.start).toBeGreaterThanOrEqual(6);
    expect(win.end - win.start).toBeLessThanOrEqual(22);
    expect(win.end).toBeLessThan(30);
    expect(computeWebtoonWindow([0], 0, 0, 900)).toEqual({ start: 0, end: 0 });
  });

  it("maps scroll position to the owning page", () => {
    const offsets = buildWebtoonOffsets(10, {}, 100);
    expect(webtoonPageAt(offsets, 10, 0, 100)).toBe(0);
    expect(webtoonPageAt(offsets, 10, 350, 100)).toBe(3);
    expect(webtoonPageAt(offsets, 10, 10_000, 100)).toBe(9);
  });
});

describe("reader storage keys", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("defaults and persists the five modes", () => {
    expect(readReaderMode()).toBe("ltr");
    writeReaderMode("double-rtl");
    expect(localStorage.getItem(READER_MODE_KEY)).toBe("double-rtl");
    expect(readReaderMode()).toBe("double-rtl");
    localStorage.setItem(READER_MODE_KEY, "bogus");
    expect(readReaderMode()).toBe("ltr");
  });

  it("defaults to fit-height and persists gv_reader_fit", () => {
    expect(readReaderFit()).toBe("height");
    writeReaderFit("original");
    expect(localStorage.getItem(READER_FIT_KEY)).toBe("original");
    expect(readReaderFit()).toBe("original");
  });

  it("clamps the slideshow interval to 1–600 seconds", () => {
    expect(readSlideshowInterval()).toBe(5);
    expect(writeSlideshowInterval(0)).toBe(5);
    expect(writeSlideshowInterval(9999)).toBe(600);
    expect(localStorage.getItem(SLIDESHOW_INTERVAL_KEY)).toBe("600");
  });
});

describe("LocalPageSource", () => {
  it("resolves backend page URLs and rejects out-of-range pages", async () => {
    const source = new LocalPageSource(7, 3);
    expect(source.kind).toBe("local");
    expect(source.officialUrl()).toBeNull();
    await expect(source.page(2)).resolves.toEqual({
      index: 2,
      url: readerPagePath(7, 2),
    });
    await expect(source.page(3)).rejects.toBeInstanceOf(RangeError);
    await expect(source.page(-1)).rejects.toBeInstanceOf(RangeError);
  });
});

describe("progress writer", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces and serialises writes", async () => {
    const sent: Array<{ current_page: number; total_pages: number }> = [];
    const writer = new ProgressWriter({
      send: async (payload) => {
        sent.push(payload);
      },
      debounceMs: 100,
    });
    writer.queue(1, 20);
    writer.queue(2, 20);
    expect(sent).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(100);
    expect(sent).toEqual([{ current_page: 2, total_pages: 20 }]);
    writer.dispose();
  });

  it("retries a failed PUT until it succeeds", async () => {
    const sent: Array<{ current_page: number; total_pages: number }> = [];
    let attempts = 0;
    const writer = new ProgressWriter({
      send: async (payload) => {
        sent.push(payload);
        attempts += 1;
        if (attempts === 1) throw new Error("500");
      },
      debounceMs: 10,
      retryDelayMs: 50,
    });
    writer.queue(4, 20, { immediate: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(sent).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(50);
    expect(sent).toHaveLength(2);
    expect(sent[1]).toEqual({ current_page: 4, total_pages: 20 });
    writer.dispose();
  });

  it("keeps the newest intent when a write fails", async () => {
    const sent: Array<{ current_page: number; total_pages: number }> = [];
    let attempts = 0;
    const writer = new ProgressWriter({
      send: async (payload) => {
        sent.push(payload);
        attempts += 1;
        if (attempts === 1) throw new Error("500");
      },
      debounceMs: 10,
      retryDelayMs: 20,
    });
    writer.queue(1, 20, { immediate: true });
    await vi.advanceTimersByTimeAsync(0);
    writer.queue(7, 20, { immediate: true });
    await vi.advanceTimersByTimeAsync(20);
    expect(sent.at(-1)).toEqual({ current_page: 7, total_pages: 20 });
    writer.dispose();
  });
});
