import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import {
  DEFAULT_ONLINE_FILTERS,
  ONLINE_CATEGORY_ALL,
  ONLINE_DEFAULTS_KEY,
  enabledCategories,
  filtersToQuery,
  loadOnlineDefaults,
  maskFromEnabled,
  mergeDownloadBadge,
  normalizeFilters,
  parseFiltersFromQuery,
  saveOnlineDefaults,
  toggleCategory,
  useOnlineStore,
} from "@/stores/online";

const searchMock = vi.hoisted(() => vi.fn());

vi.mock("@/api/eh", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/eh")>();
  return { ...actual, searchOnline: searchMock };
});

function searchItem(gid: number) {
  return {
    gid,
    token: `tok${gid}`,
    title: `Gallery ${gid}`,
    category: "manga",
    pages: 10,
    rating: 4.5,
  };
}

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  searchMock.mockReset();
});

describe("category bitmask", () => {
  it("maps the UI checkbox set to ExHentai f_cats", () => {
    expect(maskFromEnabled([])).toBe(0);
    expect(
      maskFromEnabled([
        "doujinshi",
        "manga",
        "artistcg",
        "gamecg",
        "western",
        "non-h",
        "image_set",
        "cosplay",
        "asianporn",
        "misc",
      ]),
    ).toBe(0);
    expect(maskFromEnabled(["manga"])).toBe(ONLINE_CATEGORY_ALL ^ 2);
    expect(enabledCategories(ONLINE_CATEGORY_ALL ^ 2)).toEqual(["manga"]);
  });

  it("toggles one category without losing the others", () => {
    const onlyManga = maskFromEnabled(["manga"]);
    const noManga = toggleCategory(onlyManga, "manga");
    expect(noManga).toBe(0);
    const withoutMisc = toggleCategory(0, "misc");
    expect(enabledCategories(withoutMisc)).not.toContain("misc");
  });
});

describe("filters", () => {
  it("normalises unknown values and clamps the mask", () => {
    expect(
      normalizeFilters({
        q: "  foo  ",
        category: 9999,
        min_rating: 9,
        list: "bogus" as never,
        tl: 99,
      }),
    ).toEqual({
      q: "foo",
      category: ONLINE_CATEGORY_ALL,
      min_rating: 5,
      list: "search",
      tl: 15,
    });
  });

  it("only keeps tl for toplist and omits default query values", () => {
    expect(filtersToQuery(DEFAULT_ONLINE_FILTERS)).toEqual({});
    expect(filtersToQuery({ ...DEFAULT_ONLINE_FILTERS, list: "toplist", tl: 12 })).toEqual({
      list: "toplist",
      tl: "12",
    });
  });

  it("parses route queries without inventing filters", () => {
    expect(parseFiltersFromQuery({ q: "abc", category: "1021" })).toEqual({
      q: "abc",
      category: 1021,
    });
    expect(parseFiltersFromQuery(new URLSearchParams("list=popular"))).toEqual({
      list: "popular",
    });
  });
});

describe("default filter persistence", () => {
  it("round-trips gv_online_defaults", () => {
    const filters = normalizeFilters({
      q: "tag:foo",
      category: 1021,
      min_rating: 4,
      list: "toplist",
      tl: 13,
    });
    saveOnlineDefaults(filters);
    expect(JSON.parse(localStorage.getItem(ONLINE_DEFAULTS_KEY) ?? "{}")).toEqual(filters);
    expect(loadOnlineDefaults()).toEqual(filters);
  });

  it("falls back to defaults for missing or corrupt storage", () => {
    expect(loadOnlineDefaults()).toEqual(DEFAULT_ONLINE_FILTERS);
    localStorage.setItem(ONLINE_DEFAULTS_KEY, "{not json");
    expect(loadOnlineDefaults()).toEqual(DEFAULT_ONLINE_FILTERS);
  });
});

describe("download badge mapping", () => {
  it("maps task states to badge tones", () => {
    expect(mergeDownloadBadge("downloading")?.tone).toBe("primary");
    expect(mergeDownloadBadge("pending")?.key).toBe("queued");
    expect(mergeDownloadBadge("failed")?.tone).toBe("error");
    expect(mergeDownloadBadge("success")).toBeNull();
  });
});

describe("cursor continuation", () => {
  it("appends the next cursor page and de-duplicates by gid", async () => {
    searchMock
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(1), searchItem(2)],
        next: "1-2",
      })
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(2), searchItem(3)],
        next: null,
      });

    const store = useOnlineStore();
    store.clearCache();
    const resumed = store.start({ ...DEFAULT_ONLINE_FILTERS });
    expect(resumed).toBe(false);

    await vi.waitFor(() => expect(store.loading).toBe(false));
    expect(store.items.map((item) => item.gid)).toEqual([1, 2]);
    expect(store.hasMore).toBe(true);

    await store.loadMore();
    expect(searchMock.mock.calls[1][0].next).toBe("1-2");
    expect(store.items.map((item) => item.gid)).toEqual([1, 2, 3]);
    expect(store.hasMore).toBe(false);
  });

  it("replaces the page with next/prev cursors and keeps the prev cursor", async () => {
    searchMock
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(1), searchItem(2)],
        next: "1-2",
        prev: null,
      })
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(3)],
        next: "3-4",
        prev: "2-2",
      })
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(1)],
        next: "1-2",
        prev: null,
      });

    const store = useOnlineStore();
    store.clearCache();
    store.start({ ...DEFAULT_ONLINE_FILTERS });
    await vi.waitFor(() => expect(store.loading).toBe(false));
    expect(store.hasPrev).toBe(false);

    await store.goNext();
    expect(searchMock.mock.calls[1][0].next).toBe("1-2");
    expect(store.items.map((item) => item.gid)).toEqual([3]);
    expect(store.prevCursor).toBe("2-2");
    expect(store.hasPrev).toBe(true);

    await store.goPrev();
    expect(searchMock.mock.calls[2][0].prev).toBe("2-2");
    expect(searchMock.mock.calls[2][0].next).toBeNull();
    expect(store.items.map((item) => item.gid)).toEqual([1]);
  });

  it("sends date jumps with the current cursor", async () => {
    searchMock
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(1)],
        next: "1-2",
        prev: null,
      })
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(2)],
        next: "3-4",
        prev: "1-2",
      });

    const store = useOnlineStore();
    store.clearCache();
    store.start({ ...DEFAULT_ONLINE_FILTERS });
    await vi.waitFor(() => expect(store.loading).toBe(false));

    await store.jumpDate({ jump: "1m" });
    expect(searchMock.mock.calls[1][0].next).toBe("1-2");
    expect(searchMock.mock.calls[1][0].jump).toBe("1m");
    expect(store.jump).toBe("1m");

    searchMock.mockResolvedValueOnce({
      state: "ok",
      items: [searchItem(2)],
      next: "3-4",
      prev: "1-2",
    });
    await store.jumpDate({ seek: "2024-02-29" });
    expect(searchMock.mock.calls[2][0].seek).toBe("2024-02-29");
    expect(store.seek).toBe("2024-02-29");
  });

  it("jumps to a toplist page and replays the cursor", async () => {
    const filters = { ...DEFAULT_ONLINE_FILTERS, list: "toplist" as const, tl: 15 };
    searchMock
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(1)],
        next: "1",
        prev: null,
      })
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(3)],
        next: "3",
        prev: "1",
      })
      .mockResolvedValueOnce({
        state: "ok",
        items: [searchItem(3)],
        next: "3",
        prev: "1",
      });

    const store = useOnlineStore();
    store.clearCache();
    store.start(filters);
    await vi.waitFor(() => expect(store.loading).toBe(false));

    await store.goToPage(3);
    expect(searchMock.mock.calls[1][0].next).toBe("2");
    expect(store.currentCursor).toBe("2");

    // Replaying the URL cursor reuses the cached page instead of refetching.
    const resumed = store.start(filters, { cursor: "2", direction: "next" });
    expect(resumed).toBe(true);
    expect(searchMock).toHaveBeenCalledTimes(2);
    expect(store.items.map((item) => item.gid)).toEqual([3]);
  });

  it("maps auth/ban states and does not paginate them", async () => {
    searchMock.mockResolvedValueOnce({ state: "not_logged_in", items: [], next: "1-2" });
    const store = useOnlineStore();
    store.clearCache();
    store.start({ ...DEFAULT_ONLINE_FILTERS });
    await vi.waitFor(() => expect(store.loading).toBe(false));
    expect(store.state).toBe("auth");
    expect(store.hasMore).toBe(false);
  });
});
