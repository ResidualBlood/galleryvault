import { describe, expect, it } from "vitest";
import {
  collectionRowHeight,
  computeColumnCount,
  computeRowHeight,
  firstVisibleItemIndex,
  firstVisibleRow,
  LIST_ROW_HEIGHT,
  LIST_ROW_HEIGHT_COMPACT,
  scrollTopForItem,
  TABLE_ROW_HEIGHT,
} from "@/stores/library";

describe("collection row heights", () => {
  it("uses the fixed list token on desktop and the compact token below 600", () => {
    expect(collectionRowHeight("list", 1000, 1, 12, false)).toBe(LIST_ROW_HEIGHT);
    expect(collectionRowHeight("list", 390, 1, 12, true)).toBe(LIST_ROW_HEIGHT_COMPACT);
  });

  it("uses the fixed table row token", () => {
    expect(collectionRowHeight("table", 1000, 1)).toBe(TABLE_ROW_HEIGHT);
    expect(collectionRowHeight("table", 390, 1)).toBe(TABLE_ROW_HEIGHT);
  });

  it("keeps grid rows on the cover + info + gutter formula", () => {
    const width = 984;
    const columns = computeColumnCount(width);
    expect(collectionRowHeight("grid", width, columns)).toBe(
      computeRowHeight(width, columns),
    );
    expect(collectionRowHeight("grid", width, 6)).toBeGreaterThan(
      collectionRowHeight("grid", 600, 6),
    );
  });
});

describe("view switch anchoring", () => {
  const canvasTop = 700;

  it("finds the first visible row from the scroll offset", () => {
    expect(firstVisibleRow(canvasTop, canvasTop, 152)).toBe(0);
    expect(firstVisibleRow(canvasTop + 151, canvasTop, 152)).toBe(0);
    expect(firstVisibleRow(canvasTop + 152, canvasTop, 152)).toBe(1);
    expect(firstVisibleRow(0, canvasTop, 152)).toBe(0);
  });

  it("converts a row to an item index using the column count", () => {
    expect(firstVisibleItemIndex(canvasTop + 152 * 3, canvasTop, 152, 4)).toBe(12);
    expect(firstVisibleItemIndex(canvasTop + 100, canvasTop, 152, 1)).toBe(0);
  });

  it("round-trips an item index back to the same scroll offset", () => {
    const item = 40;
    const rowHeight = 200;
    const columns = 4;
    const offset = scrollTopForItem(item, rowHeight, columns, canvasTop);
    expect(offset).toBe(canvasTop + 10 * rowHeight);
    expect(firstVisibleItemIndex(offset, canvasTop, rowHeight, columns)).toBe(item);
  });

  it("keeps the anchor when the target view has a single column", () => {
    const item = 17;
    const offset = scrollTopForItem(item, 152, 1, canvasTop);
    expect(firstVisibleItemIndex(offset, canvasTop, 152, 1)).toBe(item);
  });

  it("never returns a negative scroll offset", () => {
    expect(scrollTopForItem(0, 56, 1, 0)).toBe(0);
  });
});
