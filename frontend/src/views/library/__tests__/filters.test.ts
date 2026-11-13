import { describe, expect, it } from "vitest";
import {
  activeConditions,
  activeFilterCount,
  appendTagCondition,
  defaultFilters,
  filtersFromQuery,
  filtersToUrlQuery,
  hasAdvancedFilters,
  languageFromTags,
  removeTagToken,
  tagTokenToTag,
  toGalleryQuery,
  withLanguageTag,
} from "../filters";

describe("library filters and URL", () => {
  it("round-trips every filter through the route query", () => {
    const query = {
      q: "dragon",
      tags: "female:sole female,male:sole male",
      category: "manga",
      read_status: "unread",
      order_by: "title_asc",
      page_min: "20",
      page_max: "80",
      min_rating: "4",
      size_min: "5",
      size_max: "50",
      posted_from: "2026-01-01",
      posted_to: "2026-02-01",
      uploader: "uploader-1",
      image_quality: "original",
      min_local_rating: "3",
      list_id: "7",
      page_size: "100",
    };
    const filters = filtersFromQuery(query, 50);
    expect(filters).toMatchObject({
      term: "dragon",
      tags: "female:sole female,male:sole male",
      category: "manga",
      readStatus: "unread",
      orderBy: "title_asc",
      pageMin: "20",
      pageMax: "80",
      minRating: "4",
      sizeMin: "5",
      sizeMax: "50",
      postedFrom: "2026-01-01",
      postedTo: "2026-02-01",
      uploader: "uploader-1",
      imageQuality: "original",
      minLocalRating: "3",
      listId: "7",
      pageSize: 100,
    });

    const url = filtersToUrlQuery(filters, { tag_mode: "and", tag_match: "exact" });
    expect(url).toEqual({ ...query, tag_mode: "and", tag_match: "exact" });
  });

  it("drops empty values but keeps the page size and tag mode", () => {
    const filters = { ...defaultFilters(50), term: "  ", category: "" };
    const url = filtersToUrlQuery(filters, { tag_mode: "and" });
    expect(url).toEqual({ order_by: "id_desc", page_size: "50", tag_mode: "and" });
  });

  it("does not leave empty tag_mode / tag_match keys in the URL", () => {
    const url = filtersToUrlQuery(defaultFilters(50), { tag_mode: "", tag_match: "" });
    expect(url).toEqual({ order_by: "id_desc", page_size: "50" });
  });

  it("reads the legacy min_pages / max_pages aliases", () => {
    const filters = filtersFromQuery({ min_pages: "12", max_pages: "40" }, 50);
    expect(filters.pageMin).toBe("12");
    expect(filters.pageMax).toBe("40");
  });

  it("clamps an unusable page size to the fallback", () => {
    expect(filtersFromQuery({ page_size: "0" }, 50).pageSize).toBe(50);
    expect(filtersFromQuery({}, 24).pageSize).toBe(24);
  });
});

describe("active conditions", () => {
  it("counts exactly the rendered chips and ignores sort / page size", () => {
    const filters = {
      ...defaultFilters(100),
      term: "dragon",
      tags: "female:sole female,male:sole male",
      category: "manga",
      readStatus: "unread",
      orderBy: "title_asc",
      pageMin: "20",
      uploader: "uploader-1",
    };
    const conditions = activeConditions(filters);
    expect(conditions.map((entry) => entry.kind)).toEqual([
      "q",
      "tag",
      "tag",
      "category",
      "read_status",
      "page_min",
      "uploader",
    ]);
    expect(activeFilterCount(filters)).toBe(conditions.length);
    expect(activeFilterCount(filters)).toBe(7);
  });

  it("treats the page size, order and blank fields as inactive", () => {
    const filters = { ...defaultFilters(500), orderBy: "file_size_desc", uploader: "  " };
    expect(activeFilterCount(filters)).toBe(0);
    expect(hasAdvancedFilters(filters)).toBe(false);
  });

  it("flags the panel-only fields for auto-open", () => {
    expect(hasAdvancedFilters({ ...defaultFilters(), pageMin: "5" })).toBe(true);
    expect(hasAdvancedFilters({ ...defaultFilters(), listId: "3" })).toBe(true);
    expect(hasAdvancedFilters({ ...defaultFilters(), tags: "female:x" })).toBe(false);
  });
});

describe("tag conditions", () => {
  it("appends a tag and pins tag_mode=and", () => {
    const first = appendTagCondition("", { namespace: "female", name: "sole female" });
    expect(first).toEqual({ tags: "female:sole female", tag_mode: "and" });

    const second = appendTagCondition(first, { namespace: "male", name: "sole male" });
    expect(second).toEqual({
      tags: "female:sole female,male:sole male",
      tag_mode: "and",
    });
  });

  it("is idempotent and flips an excluded tag", () => {
    const tag = { namespace: "female", name: "sole female" };
    const query = { tags: "male:x,female:sole female", tag_mode: "and" };
    expect(appendTagCondition(query, tag).tags).toBe("male:x,female:sole female");
    expect(appendTagCondition(query, tag, { exclude: true }).tags).toBe(
      "male:x,-female:sole female",
    );
    expect(
      appendTagCondition("-female:sole female", tag, { exclude: true }).tags,
    ).toBe("-female:sole female");
  });

  it("removes one token without touching the rest", () => {
    expect(removeTagToken("a:1,b:2,c:3", "b:2")).toBe("a:1,c:3");
    expect(removeTagToken("a:1", "b:2")).toBe("a:1");
  });

  it("parses a raw token for chip labels", () => {
    expect(tagTokenToTag("female:sole female")).toEqual({
      namespace: "female",
      name: "sole female",
    });
    expect(tagTokenToTag("-male:x")).toEqual({ namespace: "male", name: "x" });
    expect(tagTokenToTag("solo")).toEqual({ namespace: null, name: "solo" });
  });
});

describe("language filter", () => {
  it("replaces the language token only", () => {
    const tags = "female:x,language:chinese,male:y";
    expect(withLanguageTag(tags, "english")).toBe("female:x,male:y,language:english");
    expect(withLanguageTag(tags, "")).toBe("female:x,male:y");
    expect(languageFromTags(tags)).toBe("chinese");
    expect(languageFromTags("female:x")).toBe("");
  });
});

describe("gallery request parameters", () => {
  it("converts MB sizes and numeric fields", () => {
    const filters = {
      ...defaultFilters(50),
      pageMin: "10",
      pageMax: "abc",
      sizeMin: "1.5",
      sizeMax: "0",
      minRating: "4.5",
      minLocalRating: "3",
      listId: "9",
    };
    expect(toGalleryQuery(filters)).toMatchObject({
      page_min: 10,
      page_max: undefined,
      size_min: 1572864,
      size_max: 0,
      min_rating: 4.5,
      min_local_rating: 3,
      list_id: 9,
      page_size: 50,
    });
  });
});
