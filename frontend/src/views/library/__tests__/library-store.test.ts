import { describe, expect, it } from "vitest";
import { withTagLimit, type GalleryListQuery } from "@/stores/library";

/**
 * `withTagLimit` lives in the shared list store but is what the library page
 * relies on for its inline tags (be-list-tags): every row must carry the full
 * tag list, so the request pins `tags_limit=0` unless a caller overrides it.
 */
describe("withTagLimit", () => {
  it("pins tags_limit=0 so list rows carry every tag", () => {
    const query: GalleryListQuery = { page_size: 50, tags: "female:x" };
    expect(withTagLimit(query)).toEqual({
      page_size: 50,
      tags: "female:x",
      tags_limit: 0,
    });
  });

  it("adds the page number and keeps an explicit limit", () => {
    const query: GalleryListQuery = { page_size: 24, tags_limit: 4 };
    expect(withTagLimit(query, 3)).toEqual({
      page_size: 24,
      tags_limit: 4,
      page: 3,
    });
  });

  it("does not mutate the caller's query", () => {
    const query: GalleryListQuery = { page_size: 24 };
    withTagLimit(query, 2);
    expect(query).toEqual({ page_size: 24 });
  });
});
