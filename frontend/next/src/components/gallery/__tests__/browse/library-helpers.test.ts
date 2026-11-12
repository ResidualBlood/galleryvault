import { describe, expect, it } from "vitest";
import {
  buildGalleryQuery,
  buildGalleryQueryString,
  canAutoRetry,
  clampPageSize,
  computeColumnCount,
  computeColumnWidth,
  computeRowHeight,
  MAX_INFINITE_ERRORS,
  mergeUniqueById,
  normalizeQuery,
  queryCacheKey,
  progressPercent,
  formatBytes,
} from "@/stores/library";
import type { GalleryItem } from "@/api/library";

function item(id: number): GalleryItem {
  return {
    id,
    gid: id,
    token: "token",
    title: `Gallery ${id}`,
    category: "doujinshi",
    page_count: 20,
    cover_url: null,
    tags: [],
  };
}

describe("virtual grid column math", () => {
  it("always returns at least one column", () => {
    expect(computeColumnCount(0)).toBe(1);
    expect(computeColumnCount(-10)).toBe(1);
    expect(computeColumnCount(Number.NaN)).toBe(1);
    expect(computeColumnCount(100)).toBe(1);
  });

  it("fits as many 152px cards as the row allows", () => {
    expect(computeColumnCount(163)).toBe(1);
    expect(computeColumnCount(164)).toBe(1);
    expect(computeColumnCount(316)).toBe(2);
    expect(computeColumnCount(390)).toBe(2);
    expect(computeColumnCount(900)).toBe(5);
    expect(computeColumnCount(1280)).toBe(7);
  });

  it("derives card width and row height from the column count", () => {
    expect(computeColumnWidth(390, 2, 12)).toBe(189);
    expect(computeColumnWidth(390, 2, 12) * (4 / 3) + 76 + 12).toBeCloseTo(
      computeRowHeight(390, 2, 12),
      5,
    );
    expect(computeRowHeight(390, 2, 12)).toBe(340);
  });
});

describe("gallery query construction", () => {
  it("clamps page size to the backend range", () => {
    expect(clampPageSize(undefined)).toBe(24);
    expect(clampPageSize("0")).toBe(24);
    expect(clampPageSize("50")).toBe(50);
    expect(clampPageSize(9999)).toBe(500);
  });

  it("omits empty values and keeps page_size", () => {
    const query = buildGalleryQuery({
      page: 2,
      page_size: 50,
      q: "dragon",
      tags: "",
      category: undefined,
      order_by: "title_asc",
    });
    expect(query).toEqual({
      page: "2",
      page_size: "50",
      q: "dragon",
      order_by: "title_asc",
    });
    expect(buildGalleryQueryString({ page_size: 50, q: "a b" })).toBe(
      "page_size=50&q=a+b",
    );
  });

  it("normalizes query and drops blank optional filters", () => {
    const normalized = normalizeQuery(
      {
        q: "  ",
        tags: "",
        category: "",
        order_by: "",
        page_size: 9999,
        page: 3,
      },
      50,
    );
    expect(normalized).toEqual({ page_size: 500, page: 3 });
  });

  it("keys the cache without the page number", () => {
    const first = queryCacheKey({ page: 1, page_size: 24, q: "x" });
    const second = queryCacheKey({ page: 9, page_size: 24, q: "x" });
    expect(first).toBe(second);
  });
});

describe("infinite scroll limits", () => {
  it("allows auto retry for the first five failures only", () => {
    expect(MAX_INFINITE_ERRORS).toBe(5);
    expect([0, 1, 2, 3, 4].every(canAutoRetry)).toBe(true);
    expect(canAutoRetry(5)).toBe(false);
    expect(canAutoRetry(6)).toBe(false);
  });
});

describe("list helpers", () => {
  it("deduplicates pages by gallery id and keeps existing order", () => {
    const merged = mergeUniqueById([item(1), item(2)], [item(2), item(3)]);
    expect(merged.map((entry) => entry.id)).toEqual([1, 2, 3]);
  });

  it("calculates reading progress and formats sizes", () => {
    expect(progressPercent(0, 100)).toBe(1);
    expect(progressPercent(49, 100)).toBe(50);
    expect(progressPercent(-1, 0)).toBe(0);
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(0)).toBe("0.0 B");
    expect(formatBytes(null)).toBe("");
  });
});
