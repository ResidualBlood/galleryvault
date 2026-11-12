import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useFavoritesStore } from "@/stores/favorites";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function addResult(overrides: Record<string, unknown> = {}) {
  return {
    gids: [42],
    target_favcat: 3,
    cloud_ok: true,
    cloud_added: 1,
    cloud_failed: [],
    successful_gids: [42],
    local_added: 1,
    ...overrides,
  };
}

describe("favorites store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("does not update state when the cloud request fails with HTTP 500", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "boom" }, 500)),
    );
    const store = useFavoritesStore();
    store.ensure(42, { favorited: false, favcat: null });

    await expect(store.add(42, "token-42", 3)).rejects.toMatchObject({ status: 500 });

    expect(store.get(42).favorited).toBe(false);
    expect(store.get(42).favcat).toBeNull();
    expect(store.get(42).pending).toBe(false);
  });

  it("only marks favorited after successful_gids contains the gid", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(addResult()));
    vi.stubGlobal("fetch", fetchMock);
    const store = useFavoritesStore();

    const result = await store.add(42, "token-42", 3);

    expect(result).toEqual({ ok: true, cloudFailed: [] });
    expect(store.get(42)).toMatchObject({ favorited: true, favcat: 3, pending: false });
    expect(localStorage.getItem("gv_default_favcat")).toBe("3");

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      gid: 42,
      token: "token-42",
      target_favcat: 3,
      note: "",
    });
  });

  it("treats a 200 with cloud_failed as failure without touching state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          addResult({ cloud_ok: false, cloud_failed: [42], successful_gids: [], local_added: 0 }),
        ),
      ),
    );
    const store = useFavoritesStore();

    const result = await store.add(42, "token-42", 3);

    expect(result.ok).toBe(false);
    expect(result.cloudFailed).toEqual([42]);
    expect(store.get(42).favorited).toBe(false);
  });

  it("de-duplicates rapid clicks into a single request", async () => {
    let resolve!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const store = useFavoritesStore();

    const first = store.add(42, "token-42", 3);
    const second = store.add(42, "token-42", 3);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolve(jsonResponse(addResult()));
    await expect(Promise.all([first, second])).resolves.toEqual([
      { ok: true, cloudFailed: [] },
      { ok: true, cloudFailed: [] },
    ]);
    expect(store.get(42).favorited).toBe(true);
  });

  it("keeps state after a failed move and updates it after a successful remove", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(addResult()))
      .mockResolvedValueOnce(
        jsonResponse(addResult({ target_favcat: 5, cloud_ok: false, cloud_failed: [42] })),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          gids: [42],
          cloud_ok: true,
          cloud_failed: [],
          successful_gids: [42],
          local_removed: 1,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const store = useFavoritesStore();

    await store.add(42, "token-42", 3);
    const moved = await store.move(42, 5);
    expect(moved.ok).toBe(false);
    expect(store.get(42)).toMatchObject({ favorited: true, favcat: 3 });

    const removed = await store.remove(42);
    expect(removed.ok).toBe(true);
    expect(store.get(42).favorited).toBe(false);
  });
});
