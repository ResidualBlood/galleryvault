import { describe, expect, it } from "vitest";
import {
  DEFAULT_FAV_ORDER,
  FAV_LIST_FILTER_KEYS,
  activeFavFilterCount,
  buildFavListParams,
  emptyFavListFilters,
  favListQuery,
  filtersFromQuery,
  megabytesToBytes,
  tagsWithLanguage,
  type FavListFilters,
} from "../filters";

function fullFilters(): FavListFilters {
  return {
    ...emptyFavListFilters(50),
    q: "dragon",
    category: "manga",
    order_by: "posted_at_desc",
    read_status: "unread",
    page_min: "10",
    page_max: "90",
    min_rating: "4.5",
    size_min: "1.5",
    size_max: "20",
    posted_from: "2025-01-01",
    posted_to: "2025-12-31",
    uploader: "artist",
    image_quality: "original",
    language: "chinese",
    min_local_rating: "3",
    state: "local",
    page: 3,
    page_size: 50,
    tags: "female:sole female",
  };
}

describe("favorites filter constructor", () => {
  it("exposes exactly the 15 legacy filters", () => {
    expect(FAV_LIST_FILTER_KEYS).toHaveLength(15);
    expect(new Set(FAV_LIST_FILTER_KEYS).size).toBe(15);
  });

  it("routes all 15 filters through buildFavListParams", () => {
    const params = buildFavListParams(fullFilters());
    for (const key of [
      "q",
      "category",
      "order_by",
      "read_status",
      "page_min",
      "page_max",
      "min_rating",
      "size_min",
      "size_max",
      "posted_from",
      "posted_to",
      "uploader",
      "image_quality",
      "min_local_rating",
    ]) {
      expect(params.get(key), key).not.toBeNull();
    }
    // Language is the 15th filter, encoded into the backend's tags parameter.
    expect(params.get("tags")).toContain("language:chinese");
    expect(params.get("page")).toBe("3");
    expect(params.get("page_size")).toBe("50");
    expect(params.get("state")).toBe("local");
  });

  it("converts MiB inputs to bytes and merges language into tags", () => {
    const params = buildFavListParams(fullFilters());
    expect(params.get("size_min")).toBe("1572864");
    expect(params.get("size_max")).toBe("20971520");
    expect(megabytesToBytes("1.5")).toBe("1572864");
    expect(tagsWithLanguage("female:sole female", "chinese")).toBe(
      "female:sole female,language:chinese",
    );
    expect(tagsWithLanguage("language:japanese,female:x", "chinese")).toBe(
      "female:x,language:chinese",
    );
  });

  it("omits defaults but keeps the page and page_size", () => {
    const params = buildFavListParams(emptyFavListFilters(24));
    expect(params.get("page")).toBe("1");
    expect(params.get("page_size")).toBe("24");
    expect(params.get("state")).toBe("all");
    expect(params.get("order_by")).toBeNull();
    expect(params.get("q")).toBeNull();
    expect(params.get("tags")).toBeNull();
    // The collection surface renders every tag, so truncation is disabled.
    expect(params.get("tags_limit")).toBe("0");
    expect(activeFavFilterCount(emptyFavListFilters())).toBe(0);
  });

  it("round-trips the router query without double-converting sizes", () => {
    const filters = fullFilters();
    const query = favListQuery(filters);
    expect(query.order_by).toBe("posted_at_desc");
    expect(query.size_min).toBe("1.5");
    expect(query.language).toBe("chinese");

    const restored = filtersFromQuery(query, 24);
    expect(restored).toMatchObject({
      q: filters.q,
      category: filters.category,
      order_by: filters.order_by,
      read_status: filters.read_status,
      page_min: filters.page_min,
      page_max: filters.page_max,
      min_rating: filters.min_rating,
      size_min: filters.size_min,
      size_max: filters.size_max,
      posted_from: filters.posted_from,
      posted_to: filters.posted_to,
      uploader: filters.uploader,
      image_quality: filters.image_quality,
      language: filters.language,
      min_local_rating: filters.min_local_rating,
      state: filters.state,
      page: filters.page,
      page_size: filters.page_size,
    });
    expect(buildFavListParams(restored).get("size_min")).toBe("1572864");
  });

  it("counts active filters and reads legacy language tags", () => {
    expect(activeFavFilterCount(fullFilters())).toBe(15);
    const fromLegacy = filtersFromQuery({ tags: "language:korean", state: "cloud" });
    expect(fromLegacy.language).toBe("korean");
    expect(fromLegacy.state).toBe("cloud");
    expect(filtersFromQuery({ order_by: "title_asc" }).order_by).toBe("title_asc");
    expect(filtersFromQuery({}).order_by).toBe(DEFAULT_FAV_ORDER);
  });
});
