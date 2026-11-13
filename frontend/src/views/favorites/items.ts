/**
 * Adapters between `GET /api/favorites/{favcat}/items` and the shared
 * collection surface.
 *
 * The single-folder page no longer draws its own `.fav-card`: every entry is
 * converted into the same `GalleryItem` the library / browse pages use, so the
 * card, list row and table row (and their tag behaviour) come from
 * `GalleryCollection`. Keep this file free of Vue state so the mapping stays
 * unit-testable.
 */
import type { GalleryItem } from "@/api/library";
import type { FavoriteItem } from "@/api/favorites";
import type { GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
import type { SortState, TableColumn } from "@/components/gallery/table-columns";

type Translate = (key: string, named?: Record<string, unknown>) => string;

/** Fixed category colour table (PLAN polish §P5: `--gv-cat-*`, values fixed). */
const CATEGORY_TOKENS: Record<string, string> = {
  doujinshi: "--gv-cat-doujinshi",
  manga: "--gv-cat-manga",
  artistcg: "--gv-cat-artistcg",
  gamecg: "--gv-cat-gamecg",
  western: "--gv-cat-western",
  "non-h": "--gv-cat-nonh",
  nonh: "--gv-cat-nonh",
  image_set: "--gv-cat-imageset",
  imageset: "--gv-cat-imageset",
  cosplay: "--gv-cat-cosplay",
  asianporn: "--gv-cat-asianporn",
  misc: "--gv-cat-misc",
  other: "--gv-cat-other",
  private: "--gv-cat-private",
  deleted: "--gv-cat-other",
};

/** Category label key under `legacy.*`; mirrors GalleryCard / GalleryTableRow. */
const CATEGORY_LABELS: Record<string, string> = {
  doujinshi: "catDoujinshi",
  manga: "catManga",
  artistcg: "catArtistcg",
  gamecg: "catGamecg",
  western: "catWestern",
  "non-h": "catNonH",
  nonh: "catNonH",
  image_set: "catImageSet",
  imageset: "catImageSet",
  cosplay: "catCosplay",
  asianporn: "catAsianporn",
  misc: "catMisc",
  other: "catMisc",
  private: "catMisc",
  deleted: "catDeleted",
};

export function categoryToken(category: string | null | undefined): string {
  return CATEGORY_TOKENS[category ?? ""] ?? "--gv-cat-misc";
}

export function categoryLabelKey(category: string | null | undefined): string {
  return CATEGORY_LABELS[category ?? ""] ?? "catMisc";
}

export function categoryBadge(
  category: string | null | undefined,
  t: Translate,
): GalleryBadge {
  const label = t(`legacy.${categoryLabelKey(category)}`);
  return {
    label,
    tone: "category",
    colorToken: categoryToken(category),
    title: label,
  };
}

/**
 * One favourite → the collection item type.
 *
 * `id` is the ExHentai gid because that is what the selection and the
 * download / move / remove endpoints speak; the local gallery id travels in
 * `favorite_category`-independent `gid`/`token` and is resolved on click.
 * The note has no field of its own in `GalleryItem`, so it fills the meta name
 * (the shared card already renders size + date next to it).
 */
export function favoriteToGalleryItem(item: FavoriteItem): GalleryItem {
  const tags = Array.isArray(item.tags) ? item.tags : [];
  return {
    id: item.gid,
    gid: item.gid,
    token: item.token || null,
    title: item.title?.trim() || `gid ${item.gid}`,
    category: item.category ?? "misc",
    page_count: item.page_count ?? 0,
    cover_url: item.cover_url ?? null,
    tags,
    tag_count: tags.length,
    uploader: item.note?.trim() || null,
    // The favourites payload has no posted date; the card's meta date slot
    // shows when the gallery was first favourited instead of a bare "—".
    posted_at: item.first_seen_at ?? null,
    file_size: item.file_size ?? null,
    favorite: true,
    favorite_category: item.favcat,
    in_library: item.is_local,
    local_note: item.note,
  };
}

/** Badge strip: local / cloud source first, category second. */
export function favoriteBadges(item: GalleryItem, t: Translate): GalleryBadge[] {
  const source = item.in_library
    ? t("favorites.list.local")
    : t("favorites.list.cloud");
  return [
    {
      label: source,
      tone: item.in_library ? "primary" : "tertiary",
      title: source,
    },
    categoryBadge(item.category, t),
  ];
}

/**
 * Folder heading fallback (audit FL-04): an unnamed slot reads
 * "收藏夹 N" instead of `#N`, and no second `#N` badge is appended.
 */
export function favoriteFolderTitle(
  name: string | null | undefined,
  favcat: number,
  t: Translate,
): string {
  const trimmed = (name ?? "").trim();
  return trimmed || t("favorites.list.fallbackName", { n: favcat });
}

/**
 * Table columns for one favourite folder.
 *
 * Only the title column is sortable: the favourites repository accepts
 * `title_asc` / `title_desc` but has no ascending order for pages / size
 * (`favorites.py` order map), and the toolbar Select already exposes the full
 * order set. Sorting stays server-side through `order_by`.
 */
export const FAV_TABLE_COLUMNS: readonly TableColumn[] = [
  { key: "selection", labelKey: "select", width: 40, align: "center", priority: 65 },
  { key: "cover", labelKey: "cover", width: 56, align: "center", priority: 100, pinned: true },
  {
    key: "title",
    labelKey: "title",
    minWidth: 160,
    flex: 1,
    align: "start",
    priority: 100,
    pinned: true,
    sortKey: "title",
    defaultDirection: "asc",
  },
  { key: "category", labelKey: "category", width: 96, align: "start", hideBelow: 520, priority: 20 },
  { key: "tags", labelKey: "tags", minWidth: 240, flex: 0.8, align: "start", hideBelow: 640, priority: 15 },
  { key: "pages", labelKey: "pages", width: 64, align: "end", priority: 70 },
  { key: "size", labelKey: "size", width: 80, align: "end", hideBelow: 720, priority: 30 },
  { key: "status", labelKey: "status", width: 72, align: "center", hideBelow: 720, priority: 50 },
];

/** `order_by` value → table header state (title only, see above). */
export function favTableSort(orderBy: string): SortState | null {
  if (orderBy === "title_asc") return { key: "title", direction: "asc" };
  if (orderBy === "title_desc") return { key: "title", direction: "desc" };
  return null;
}

