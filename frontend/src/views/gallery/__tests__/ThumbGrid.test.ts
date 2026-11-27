import { describe, expect, it } from "vitest";
import {
  computeMetrics,
  visibleIndexRange,
} from "@/components/gallery/ThumbGrid.vue";

describe("ThumbGrid virtualization metrics", () => {
  it("keeps the rendered window below 150 nodes for a 1000-page gallery", () => {
    for (const width of [968, 640, 358]) {
      const metrics = computeMetrics(width, 1000, 96, 8);
      const range = visibleIndexRange(0, 900, metrics, 1000, 2);

      expect(metrics.columns).toBeGreaterThanOrEqual(1);
      expect(range.start).toBe(0);
      expect(range.end - range.start).toBeLessThan(150);
    }
  });

  it("moves the window with the scroll position and clamps at the end", () => {
    const metrics = computeMetrics(968, 1000, 96, 8);
    const middle = visibleIndexRange(metrics.rowHeight * 40, 900, metrics, 1000, 2);

    expect(middle.start).toBeGreaterThan(0);
    expect(middle.end).toBeLessThanOrEqual(1000);

    const bottom = visibleIndexRange(metrics.totalHeight, 900, metrics, 1000, 2);
    expect(bottom.end).toBe(1000);
  });

  it("handles an empty gallery", () => {
    const metrics = computeMetrics(960, 0, 96, 8);
    expect(metrics.rows).toBe(1);

    const range = visibleIndexRange(0, 900, metrics, 0);
    expect(range).toEqual({ start: 0, end: 0 });
  });
});
