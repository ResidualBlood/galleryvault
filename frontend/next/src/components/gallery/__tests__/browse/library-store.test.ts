import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/api/library", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/library")>();
  return { ...actual, fetchGalleries: vi.fn() };
});

import { fetchGalleries, type GalleryPage } from "@/api/library";
import { MAX_INFINITE_ERRORS, useLibraryStore } from "@/stores/library";

const mockedFetch = vi.mocked(fetchGalleries);

function page(overrides: Partial<GalleryPage> = {}): GalleryPage {
  return {
    total: 200,
    page: 1,
    page_size: 50,
    items: [],
    ...overrides,
  };
}

describe("library list store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockedFetch.mockReset();
  });

  it("stops auto loading after five consecutive failures and retries explicitly", async () => {
    mockedFetch.mockRejectedValue(new Error("boom"));
    const store = useLibraryStore();
    store.start({ page_size: 50 });

    await vi.waitFor(() => expect(store.failures).toBe(1));
    expect(mockedFetch).toHaveBeenCalledTimes(1);

    for (let attempt = 1; attempt < MAX_INFINITE_ERRORS; attempt += 1) {
      expect(await store.loadMore()).toBe(false);
    }
    expect(store.failures).toBe(MAX_INFINITE_ERRORS);
    expect(mockedFetch).toHaveBeenCalledTimes(MAX_INFINITE_ERRORS);

    expect(await store.loadMore()).toBe(false);
    expect(mockedFetch).toHaveBeenCalledTimes(MAX_INFINITE_ERRORS);

    mockedFetch.mockResolvedValue(page());
    expect(await store.retry()).toBe(true);
    expect(store.failures).toBe(0);
    expect(store.error).toBeNull();
  });

  it("appends pages and reports exhaustion", async () => {
    mockedFetch
      .mockResolvedValueOnce(
        page({
          total: 2,
          page: 1,
          page_size: 1,
          items: [
            {
              id: 1,
              gid: 1,
              token: "t",
              title: "One",
              category: "manga",
              page_count: 10,
              cover_url: null,
              tags: [],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        page({
          total: 2,
          page: 2,
          page_size: 1,
          items: [
            {
              id: 2,
              gid: 2,
              token: "t",
              title: "Two",
              category: "manga",
              page_count: 10,
              cover_url: null,
              tags: [],
            },
          ],
        }),
      );

    const store = useLibraryStore();
    store.start({ page_size: 1 });
    await vi.waitFor(() => expect(store.items).toHaveLength(1));
    expect(await store.loadMore()).toBe(true);
    expect(store.items.map((item) => item.id)).toEqual([1, 2]);
    expect(store.exhausted).toBe(true);
  });
});
