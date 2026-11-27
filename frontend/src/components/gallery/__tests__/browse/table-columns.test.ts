import { describe, expect, it } from "vitest";
import {
  BROWSE_TABLE_COLUMNS,
  LOCAL_TABLE_COLUMNS,
  columnTemplate,
  nextSortDirection,
  orderByFor,
  sortAriaState,
  tableMinWidth,
  visibleColumns,
  type TableColumn,
} from "@/components/gallery/table-columns";

function keys(columns: readonly TableColumn[]): string[] {
  return columns.map((column) => column.key);
}

describe("table column visibility", () => {
  it("keeps every column when the container is wide", () => {
    const visible = visibleColumns(LOCAL_TABLE_COLUMNS, 4000);
    expect(keys(visible)).toEqual(keys(LOCAL_TABLE_COLUMNS));
  });

  it("drops the uploader column before the 1000px container breakpoint", () => {
    const visible = keys(visibleColumns(BROWSE_TABLE_COLUMNS, 984));
    expect(visible).toContain("tags");
    expect(visible).toContain("category");
    expect(visible).toContain("pages");
    expect(visible).not.toContain("uploader");
  });

  it("drops the posted column on narrower containers", () => {
    expect(keys(visibleColumns(BROWSE_TABLE_COLUMNS, 900))).not.toContain("posted");
  });

  it("drops tags / size / rating on a drawer-narrow container", () => {
    const visible = keys(visibleColumns(LOCAL_TABLE_COLUMNS, 604));
    expect(visible).not.toContain("tags");
    expect(visible).not.toContain("size");
    expect(visible).not.toContain("rating");
    expect(visible).toContain("category");
    expect(visible).toContain("pages");
  });

  it("always fits the minimum widths so the table never scrolls", () => {
    for (const width of [400, 512, 604, 720, 800, 900, 984, 1200, 1440, 2000]) {
      const visible = visibleColumns(LOCAL_TABLE_COLUMNS, width);
      expect(tableMinWidth(visible)).toBeLessThanOrEqual(width);
    }
  });

  it("keeps cover and title even at the narrowest measured width", () => {
    const visible = keys(visibleColumns(LOCAL_TABLE_COLUMNS, 260));
    expect(visible).toContain("cover");
    expect(visible).toContain("title");
  });

  it("builds one shared grid template", () => {
    const template = columnTemplate(visibleColumns(BROWSE_TABLE_COLUMNS, 1000));
    expect(template).toContain("56px");
    expect(template).toContain("minmax(160px, 1fr)");
  });
});

describe("table sorting", () => {
  const pages = LOCAL_TABLE_COLUMNS.find((column) => column.key === "pages")!;
  const title = LOCAL_TABLE_COLUMNS.find((column) => column.key === "title")!;
  const cover = LOCAL_TABLE_COLUMNS.find((column) => column.key === "cover")!;

  it("starts numeric columns descending and text ascending", () => {
    expect(nextSortDirection(pages, null)).toBe("desc");
    expect(nextSortDirection(title, null)).toBe("asc");
  });

  it("flips the direction on the active column", () => {
    expect(nextSortDirection(pages, { key: "pages", direction: "desc" })).toBe("asc");
    expect(nextSortDirection(pages, { key: "pages", direction: "asc" })).toBe("desc");
    expect(nextSortDirection(title, { key: "pages", direction: "desc" })).toBe("asc");
  });

  it("maps to the backend order_by values", () => {
    expect(orderByFor(pages, "desc")).toBe("page_count_desc");
    expect(orderByFor(title, "asc")).toBe("title_asc");
    expect(orderByFor(cover, "asc")).toBeNull();
  });

  it("tracks aria-sort for the active header only", () => {
    expect(sortAriaState(pages, null)).toBe("none");
    expect(sortAriaState(pages, { key: "pages", direction: "desc" })).toBe("descending");
    expect(sortAriaState(title, { key: "pages", direction: "desc" })).toBe("none");
  });
});
