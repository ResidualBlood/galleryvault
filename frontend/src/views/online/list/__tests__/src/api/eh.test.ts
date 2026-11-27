import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildSearchParams,
  ehGalleryEp,
  ehPagesEp,
  fetchOnlineDetail,
  fetchOnlinePages,
  isValidCursor,
  isValidJump,
  isValidSeekDate,
  mapOnlineState,
  officialGalleryUrl,
  searchOnline,
} from "@/api/eh";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mapOnlineState", () => {
  it("maps backend auth variants to the settings state", () => {
    expect(mapOnlineState("not_logged_in")).toBe("auth");
    expect(mapOnlineState("no_exhentai_access")).toBe("auth");
    expect(mapOnlineState("auth")).toBe("auth");
  });

  it("maps challenge, ban, empty and unknown states", () => {
    expect(mapOnlineState("challenge")).toBe("challenge");
    expect(mapOnlineState("banned")).toBe("banned");
    expect(mapOnlineState("ip_banned")).toBe("banned");
    expect(mapOnlineState("ok")).toBe("ok");
    expect(mapOnlineState("empty")).toBe("empty");
    expect(mapOnlineState("rate_limited")).toBe("error");
    expect(mapOnlineState(undefined)).toBe("error");
  });
});

describe("buildSearchParams", () => {
  it("keeps search filters and the cursor", () => {
    expect(
      buildSearchParams({
        q: "  artist:foo ",
        category: 1021,
        min_rating: 4,
        list: "search",
        tl: 15,
        next: "1-2",
      }),
    ).toEqual({
      q: "artist:foo",
      category: "1021",
      min_rating: "4",
      list: "search",
      next: "1-2",
    });
  });

  it("does not send category=0 and only sends tl for toplist", () => {
    expect(buildSearchParams({ category: 0, list: "popular", tl: 15 })).toEqual({
      list: "popular",
    });
    expect(buildSearchParams({ list: "toplist", tl: 12 })).toEqual({
      list: "toplist",
      tl: "12",
    });
  });

  it("sends prev or next (not both) plus date-jump parameters", () => {
    expect(buildSearchParams({ prev: "1-2", next: "3-4", jump: "1m" })).toEqual({
      next: "3-4",
      jump: "1m",
    });
    expect(buildSearchParams({ prev: "1-2", seek: "2024-02-29" })).toEqual({
      prev: "1-2",
      seek: "2024-02-29",
    });
  });
});

describe("cursor validation", () => {
  it("accepts paginated cursors for search and numeric cursors for toplist", () => {
    expect(isValidCursor("1-2")).toBe(true);
    expect(isValidCursor("7")).toBe(true);
    expect(isValidCursor("1-2", "toplist")).toBe(false);
    expect(isValidCursor("199", "toplist")).toBe(true);
    expect(isValidCursor("200", "toplist")).toBe(false);
    expect(isValidCursor("")).toBe(false);
  });
});

describe("date-jump validation", () => {
  it("accepts the eight EH intervals and real calendar dates", () => {
    for (const value of ["1d", "3d", "1w", "2w", "1m", "6m", "1y", "2y"]) {
      expect(isValidJump(value)).toBe(true);
    }
    expect(isValidJump("2d")).toBe(false);
    expect(isValidSeekDate("2024-02-29")).toBe(true);
    expect(isValidSeekDate("2024-02-30")).toBe(false);
    expect(isValidSeekDate("2024-2-9")).toBe(false);
  });

  it("returns the prev cursor from the search response", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      void input;
      return new Response(
        JSON.stringify({
          state: "ok",
          items: [],
          next: "3-4",
          prev: "1-2",
          jump: "1m",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const data = await searchOnline({ q: "test", prev: "1-2", jump: "1m" });
    expect(String(fetchMock.mock.calls[0][0])).toContain("prev=1-2");
    expect(data.prev).toBe("1-2");
    expect(data.jump).toBe("1m");
  });
});

describe("fetch helpers", () => {
  it("normalises preview pages and requests the page cursor", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      void input;
      return new Response(
        JSON.stringify({
          state: "ok",
          p: 1,
          per_page: 20,
          total: 32,
          items: [
            { index: 20, thumb: null },
            {
              index: 21,
              thumb: { url: "https://ehgt.org/x.jpg", x: 1, y: 2, w: 3, h: 4 },
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const page = await fetchOnlinePages(123, "deadbeef", 1);

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `${ehPagesEp.path.replace("{gid}", "123").replace("{token}", "deadbeef")}?p=1`,
    );
    expect(page.per_page).toBe(20);
    expect(page.total).toBe(32);
    expect(page.items[0].thumb).toBeNull();
    expect(page.items[1].thumb).toEqual({
      url: "https://ehgt.org/x.jpg",
      x: 1,
      y: 2,
      w: 3,
      h: 4,
    });
  });

  it("returns the detail state and gallery payload", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      void input;
      return new Response(
        JSON.stringify({
          state: "ok",
          gallery: { gid: 9, token: "abc", title: "Fixture", tags: [], in_library: false },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const detail = await fetchOnlineDetail(9, "abc");

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      ehGalleryEp.path.replace("{gid}", "9").replace("{token}", "abc"),
    );
    expect(detail.state).toBe("ok");
    expect(detail.gallery?.title).toBe("Fixture");
  });

  it("builds the official ExHentai URL", () => {
    expect(officialGalleryUrl(123, "deadbeef")).toBe(
      "https://exhentai.org/g/123/deadbeef/",
    );
  });
});
