import { describe, expect, it } from "vitest";
import type { FavoriteItem } from "@/api/favorites";
import {
  FAV_TABLE_COLUMNS,
  categoryBadge,
  categoryToken,
  favTableSort,
  favoriteBadges,
  favoriteFolderTitle,
  favoriteToGalleryItem,
} from "../items";

function favorite(overrides: Partial<FavoriteItem> = {}): FavoriteItem {
  return {
    favcat: 3,
    gid: 5001,
    token: "abc123",
    title: "Sample gallery",
    title_jpn: null,
    url: "https://e-hentai.org/g/5001/abc123/",
    gallery_id: 42,
    category: "manga",
    page_count: 24,
    cover_url: null,
    file_size: 1024,
    note: "Read again",
    first_seen_at: "2025-10-01T10:00:00Z",
    is_local: true,
    tags: [
      { namespace: "female", name: "sole female", display: "单体女性" },
      { namespace: "artist", name: "someone", display: null },
    ],
    ...overrides,
  };
}

/** Mimics vue-i18n's `t`: named interpolation plus a key echo. */
function t(key: string, named?: Record<string, unknown>): string {
  if (!named) return key;
  return `${key}:${JSON.stringify(named)}`;
}

describe("favorites item adapter", () => {
  it("uses the gid as the collection id so the selection matches the API", () => {
    const item = favoriteToGalleryItem(favorite());
    expect(item.id).toBe(5001);
    expect(item.gid).toBe(5001);
    expect(item.token).toBe("abc123");
  });

  it("keeps every returned tag and reports the real count", () => {
    const item = favoriteToGalleryItem(favorite());
    expect(item.tags).toHaveLength(2);
    expect(item.tag_count).toBe(2);
  });

  it("marks local / cloud sources and keeps the note", () => {
    const local = favoriteToGalleryItem(favorite());
    const cloud = favoriteToGalleryItem(favorite({ gallery_id: null, is_local: false }));
    expect(local.in_library).toBe(true);
    expect(cloud.in_library).toBe(false);
    expect(local.local_note).toBe("Read again");
    expect(local.uploader).toBe("Read again");
    expect(local.favorite).toBe(true);
    expect(local.favorite_category).toBe(3);
    expect(local.posted_at).toBe("2025-10-01T10:00:00Z");
  });

  it("falls back to a gid title and misc category", () => {
    const item = favoriteToGalleryItem(
      favorite({ title: "   ", category: null, page_count: null, file_size: null }),
    );
    expect(item.title).toBe("gid 5001");
    expect(item.category).toBe("misc");
    expect(item.page_count).toBe(0);
    expect(item.file_size).toBeNull();
  });

  it("builds the source + category badge strip", () => {
    const badges = favoriteBadges(favoriteToGalleryItem(favorite()), t);
    expect(badges.map((badge) => badge.tone)).toEqual(["primary", "category"]);
    expect(badges[0].label).toBe("favorites.list.local");

    const cloud = favoriteBadges(
      favoriteToGalleryItem(favorite({ is_local: false })),
      t,
    );
    expect(cloud[0].tone).toBe("tertiary");
    expect(cloud[0].label).toBe("favorites.list.cloud");
  });

  it("maps the fixed category colour table", () => {
    expect(categoryToken("doujinshi")).toBe("--gv-cat-doujinshi");
    expect(categoryToken("non-h")).toBe("--gv-cat-nonh");
    expect(categoryToken(null)).toBe("--gv-cat-misc");
    expect(categoryBadge("manga", t)).toMatchObject({
      tone: "category",
      colorToken: "--gv-cat-manga",
      label: "legacy.catManga",
    });
  });
});

describe("favorites folder heading", () => {
  it("uses the folder name when present", () => {
    expect(favoriteFolderTitle("  Doujinshi ", 1, t)).toBe("Doujinshi");
  });

  it("falls back to the localised slot name instead of #N", () => {
    expect(favoriteFolderTitle("", 0, t)).toBe(
      'favorites.list.fallbackName:{"n":0}',
    );
    expect(favoriteFolderTitle(null, 7, t)).toBe(
      'favorites.list.fallbackName:{"n":7}',
    );
  });
});

describe("favorites table columns", () => {
  it("offers the three collection views through the shared column model", () => {
    expect(FAV_TABLE_COLUMNS.map((column) => column.key)).toEqual([
      "selection",
      "cover",
      "title",
      "category",
      "tags",
      "pages",
      "size",
      "status",
    ]);
  });

  it("only sorts by title (the repository has no ascending numeric order)", () => {
    const sortable = FAV_TABLE_COLUMNS.filter((column) => column.sortKey);
    expect(sortable.map((column) => column.sortKey)).toEqual(["title"]);
  });

  it("maps order_by back to the header state", () => {
    expect(favTableSort("title_asc")).toEqual({ key: "title", direction: "asc" });
    expect(favTableSort("title_desc")).toEqual({ key: "title", direction: "desc" });
    expect(favTableSort("last_seen_desc")).toBeNull();
  });
});
