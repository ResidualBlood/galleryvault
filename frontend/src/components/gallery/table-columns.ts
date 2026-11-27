/**
 * Collection table column model (DESIGN.md C18 / PLAN polish §P5).
 *
 * One immutable definition per surface; visibility is computed from the
 * *container* width (not the viewport) so the table never scrolls sideways.
 * Columns are dropped by ascending priority until the remaining minimum widths
 * fit, which also covers the persistent drawer eating 264px at 1280.
 *
 * Sorting is server-side only: `orderByFor` maps a column key plus a direction
 * to the `order_by` value accepted by `GET /api/galleries`
 * (id / posted_at / title / page_count / file_size / rating × asc / desc).
 */

export type TableAlign = "start" | "center" | "end";
export type SortDirection = "asc" | "desc";

export interface TableColumn {
  key: string;
  /** i18n key under `collection.table`. */
  labelKey: string;
  /** Fixed width in CSS px. Omit for flexible columns. */
  width?: number;
  /** Minimum width for `minmax(min, fr)` flexible columns. */
  minWidth?: number;
  /** Flex factor for flexible columns. */
  flex?: number;
  align: TableAlign;
  /** `order_by` prefix; the direction is appended. Absent = not sortable. */
  sortKey?: "title" | "posted_at" | "page_count" | "file_size" | "rating" | "id";
  /** Direction used by the first click. Numbers / dates start descending. */
  defaultDirection?: SortDirection;
  /** Hidden when the table container is narrower than this. */
  hideBelow?: number;
  /** Drop order when the minimum widths do not fit; higher survives longer. */
  priority: number;
  /** Keep this column even when the table has to shrink (cover / title). */
  pinned?: boolean;
}

export interface SortState {
  key: string;
  direction: SortDirection;
}

const NUMERIC_COLUMNS = new Set(["page_count", "file_size", "rating", "posted_at", "id"]);

function column(key: string, labelKey: string, extra: Partial<TableColumn> = {}): TableColumn {
  return { key, labelKey, align: "start", priority: 50, ...extra };
}

/** Full local-library column set; pages trim it through `visibleColumns`. */
export const LOCAL_TABLE_COLUMNS: readonly TableColumn[] = [
  column("selection", "select", { width: 40, align: "center", priority: 65 }),
  column("cover", "cover", { width: 56, align: "center", priority: 100, pinned: true }),
  column("title", "title", {
    minWidth: 160,
    flex: 1,
    priority: 100,
    pinned: true,
    sortKey: "title",
    defaultDirection: "asc",
  }),
  column("category", "category", { width: 96, hideBelow: 520, priority: 20 }),
  column("tags", "tags", { minWidth: 270, flex: 0.8, hideBelow: 640, priority: 15 }),
  column("uploader", "uploader", { width: 120, hideBelow: 1000, priority: 5 }),
  column("pages", "pages", {
    width: 64,
    align: "end",
    priority: 70,
    sortKey: "page_count",
    defaultDirection: "desc",
  }),
  column("size", "size", {
    width: 80,
    align: "end",
    hideBelow: 720,
    priority: 30,
    sortKey: "file_size",
    defaultDirection: "desc",
  }),
  column("rating", "rating", {
    width: 80,
    hideBelow: 720,
    priority: 30,
    sortKey: "rating",
    defaultDirection: "desc",
  }),
  column("posted", "posted", {
    width: 100,
    align: "end",
    hideBelow: 950,
    priority: 10,
    sortKey: "posted_at",
    defaultDirection: "desc",
  }),
  column("progress", "progress", { width: 64, align: "end", hideBelow: 720, priority: 40 }),
  column("status", "status", { width: 72, align: "center", hideBelow: 720, priority: 50 }),
  column("actions", "actions", { width: 72, align: "end", priority: 65 }),
];

/**
 * Browse ("recently added") table: no batch selection and no per-row action
 * menu on the home page, so those columns are left out entirely.
 */
export const BROWSE_TABLE_COLUMNS: readonly TableColumn[] = LOCAL_TABLE_COLUMNS.filter(
  (entry) => entry.key !== "selection" && entry.key !== "actions",
);

/** Minimum width a column needs inside the grid template. */
export function columnMinWidth(entry: TableColumn): number {
  return entry.width ?? entry.minWidth ?? 80;
}

/** Sum of the minimum widths; the table fits when this is <= container width. */
export function tableMinWidth(columns: readonly TableColumn[]): number {
  return columns.reduce((total, entry) => total + columnMinWidth(entry), 0);
}

/**
 * Columns that fit in `width`.
 *
 * `hideBelow` handles the documented breakpoints; the priority loop is the
 * safety net for the actual container width (drawer + page padding), so the
 * table can never overflow horizontally. `width <= 0` means "not measured yet"
 * and keeps every column that is not explicitly hidden.
 */
export function visibleColumns(
  columns: readonly TableColumn[],
  width: number,
): TableColumn[] {
  if (!Number.isFinite(width) || width <= 0) {
    return columns.filter((entry) => entry.hideBelow === undefined);
  }
  let visible = columns.filter((entry) => entry.hideBelow === undefined || width >= entry.hideBelow);
  while (visible.length > 1 && tableMinWidth(visible) > width) {
    const removable = visible
      .filter((entry) => !entry.pinned)
      .sort((a, b) => a.priority - b.priority);
    if (!removable.length) break;
    visible = visible.filter((entry) => entry !== removable[0]);
  }
  return visible;
}

/** CSS grid template shared by the header and every body row. */
export function columnTemplate(columns: readonly TableColumn[]): string {
  if (!columns.length) return "minmax(0, 1fr)";
  return columns
    .map((entry) => {
      if (entry.width !== undefined) return `${entry.width}px`;
      return `minmax(${entry.minWidth ?? 80}px, ${entry.flex ?? 1}fr)`;
    })
    .join(" ");
}

function isNumericColumn(entry: TableColumn): boolean {
  return entry.sortKey !== undefined && NUMERIC_COLUMNS.has(entry.sortKey);
}

/** Next direction for a header click (numeric / date columns start at desc). */
export function nextSortDirection(
  entry: TableColumn,
  current: SortState | null | undefined,
): SortDirection {
  if (current && current.key === entry.key) {
    return current.direction === "asc" ? "desc" : "asc";
  }
  if (entry.defaultDirection) return entry.defaultDirection;
  return isNumericColumn(entry) ? "desc" : "asc";
}

/** `order_by` value for a column + direction, or null when unsupported. */
export function orderByFor(entry: TableColumn, direction: SortDirection): string | null {
  if (!entry.sortKey) return null;
  return `${entry.sortKey}_${direction}`;
}

/** Sortable header label suffix key (`sortNone` / `sortAsc` / `sortDesc`). */
export function sortAriaState(
  entry: TableColumn,
  current: SortState | null | undefined,
): "ascending" | "descending" | "none" {
  if (!current || current.key !== entry.key) return "none";
  return current.direction === "asc" ? "ascending" : "descending";
}
