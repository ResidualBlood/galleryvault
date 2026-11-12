import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { onlineImagePath, type ResolvedOnlinePage } from "@/api/eh-reader";
import {
  DEFAULT_ONLINE_IMAGE_MODE,
  ONLINE_IMAGE_MODE_KEY,
  OnlineDirectPageSource,
  OnlineSourceError,
  createOnlinePageSource,
  readOnlineImageMode,
  writeOnlineImageMode,
} from "./index";

const GID = 900001;
const TOKEN = "tok900001";

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => void map.delete(key),
    setItem: (key: string, value: string) => void map.set(key, value),
  };
}

function resolved(page: number, retry = 0, ttlMs = 60_000, now = Date.now()): ResolvedOnlinePage {
  return {
    state: "ok",
    page,
    url: `https://node${retry}.hath.network:8443/${page}-${retry}.jpg`,
    width: 800,
    height: 1200,
    expires_at: new Date(now + ttlMs).toISOString(),
  };
}

describe("online image mode", () => {
  it("defaults to direct and ignores unknown stored values", () => {
    const storage = memoryStorage();
    expect(readOnlineImageMode(storage)).toBe(DEFAULT_ONLINE_IMAGE_MODE);
    expect(DEFAULT_ONLINE_IMAGE_MODE).toBe("direct");

    storage.setItem(ONLINE_IMAGE_MODE_KEY, "carrier-pigeon");
    expect(readOnlineImageMode(storage)).toBe("direct");

    expect(writeOnlineImageMode("proxy", storage)).toBe("proxy");
    expect(storage.getItem(ONLINE_IMAGE_MODE_KEY)).toBe("proxy");
    expect(readOnlineImageMode(storage)).toBe("proxy");
  });

  it("creates the matching page source for both modes", () => {
    const direct = createOnlinePageSource({
      mode: "direct",
      gid: GID,
      token: TOKEN,
      pageCount: 10,
    });
    const proxy = createOnlinePageSource({
      mode: "proxy",
      gid: GID,
      token: TOKEN,
      pageCount: 10,
    });
    expect(direct.kind).toBe("online-direct");
    expect(proxy.kind).toBe("online-proxy");
    expect(proxy.officialUrl()).toBe(
      `https://exhentai.org/g/${GID}/${TOKEN}/`,
    );
  });
});

describe("proxy source", () => {
  it("builds the 1-based image proxy URL and rejects out-of-range pages", async () => {
    const source = createOnlinePageSource({
      mode: "proxy",
      gid: GID,
      token: TOKEN,
      pageCount: 3,
    });
    const ref = await source.page(0);
    expect(ref.url).toBe(onlineImagePath(GID, TOKEN, 1));
    await expect(source.page(3)).rejects.toBeInstanceOf(RangeError);
    await expect(source.page(-1)).rejects.toBeInstanceOf(RangeError);
  });
});

describe("direct source expiry", () => {
  it("reuses a fresh URL and re-resolves once expires_at is inside the skew", async () => {
    let now = 1_000_000;
    const resolve = vi.fn(async (page: number, retry: number) =>
      resolved(page, retry, 10_000, now),
    );
    const probe = vi.fn(async () => ({ width: 800, height: 1200 }));
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 10,
      resolve,
      probe,
      now: () => now,
    });

    const first = await source.page(0);
    expect(first.url).toContain("node0");
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(resolve).toHaveBeenCalledWith(1, 0, expect.anything());

    await source.page(0);
    expect(resolve).toHaveBeenCalledTimes(1);

    // Remaining 6 s > 5 s skew: still valid.
    now += 4_000;
    expect(source.isExpired(0)).toBe(false);
    await source.page(0);
    expect(resolve).toHaveBeenCalledTimes(1);

    // Remaining 4 s <= 5 s skew: stale, resolve again.
    now += 2_000;
    expect(source.isExpired(0)).toBe(true);
    await source.page(0);
    expect(resolve).toHaveBeenCalledTimes(2);
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("treats a missing expires_at as a long-lived URL", async () => {
    const resolve = vi.fn(async (page: number) => ({
      ...resolved(page),
      expires_at: null,
    }));
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 1,
      resolve,
      probe: async () => ({ width: 600, height: 900 }),
    });
    await source.page(0);
    expect(source.isExpired(0)).toBe(false);
    await source.page(0);
    expect(resolve).toHaveBeenCalledTimes(1);
  });
});

describe("direct source retry ladder", () => {
  it("walks 0 → 1 → 2 when the first image attempts fail, then succeeds", async () => {
    const seen: number[] = [];
    const resolve = vi.fn(async (page: number, retry: number) => {
      seen.push(retry);
      return resolved(page, retry);
    });
    const probe = vi
      .fn()
      .mockRejectedValueOnce(new Error("node down"))
      .mockRejectedValueOnce(new Error("node down"))
      .mockResolvedValueOnce({ width: 800, height: 1200 });
    const events: string[] = [];
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 5,
      resolve,
      probe,
    });
    source.subscribe((event) => events.push(event.type));

    const ref = await source.page(0);
    expect(seen).toEqual([0, 1, 2]);
    expect(ref.url).toContain("node2");
    expect(events).toEqual([]);
  });

  it("gives up after retry=2 and emits `blocked` once", async () => {
    const resolve = vi.fn(async (page: number, retry: number) => resolved(page, retry));
    const probe = vi.fn(async () => {
      throw new Error("still dead");
    });
    const events: Array<{ type: string; page?: number; reason?: string }> = [];
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 5,
      resolve,
      probe,
    });
    source.subscribe((event) => events.push(event));

    await expect(source.page(2)).rejects.toMatchObject({ code: "blocked" });
    expect(resolve).toHaveBeenCalledTimes(3);
    expect(events).toEqual([{ type: "blocked", page: 2, reason: "image_failed" }]);

    // A blocked page is not retried again by a later preload call.
    await expect(source.page(2)).rejects.toBeInstanceOf(OnlineSourceError);
    expect(resolve).toHaveBeenCalledTimes(3);
  });

  it("treats a 509-sized placeholder as a dead node and retries", async () => {
    const resolve = vi.fn(async (page: number, retry: number) => resolved(page, retry));
    const probe = vi
      .fn()
      .mockResolvedValueOnce({ width: 1, height: 1 })
      .mockResolvedValueOnce({ width: 800, height: 1200 });
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 5,
      resolve,
      probe,
    });
    const ref = await source.page(0);
    expect(ref.url).toContain("node1");
    expect(resolve).toHaveBeenCalledTimes(2);
  });
});

describe("direct source 429 image_limit", () => {
  it("stops resolving and refuses later pages after the quota error", async () => {
    const resolve = vi.fn(async () => {
      throw new ApiError("image limit", {
        status: 429,
        detail: { code: "image_limit" },
      });
    });
    const events: string[] = [];
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 10,
      resolve,
      probe: async () => ({ width: 800, height: 1200 }),
    });
    source.subscribe((event) => events.push(event.type));

    await expect(source.page(0)).rejects.toMatchObject({ code: "image_limit" });
    expect(source.isThrottled).toBe(true);
    expect(events).toEqual(["quota"]);
    expect(resolve).toHaveBeenCalledTimes(1);

    await expect(source.page(1)).rejects.toMatchObject({ code: "image_limit" });
    await expect(source.page(2)).rejects.toMatchObject({ code: "image_limit" });
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(events).toEqual(["quota"]);
  });
  it("keeps already-resolved pages readable after the quota error", async () => {
    const resolve = vi.fn(async (page: number, retry: number) => {
      if (page === 2) {
        throw new ApiError("image limit", {
          status: 429,
          detail: { code: "image_limit" },
        });
      }
      return resolved(page, retry);
    });
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 10,
      resolve,
      probe: async () => ({ width: 800, height: 1200 }),
    });

    const first = await source.page(0);
    await expect(source.page(1)).rejects.toMatchObject({ code: "image_limit" });
    expect(source.isThrottled).toBe(true);

    const again = await source.page(0);
    expect(again.url).toBe(first.url);
    expect(resolve).toHaveBeenCalledTimes(2);
  });
});

describe("direct source concurrency", () => {
  it("keeps at most two resolve requests in flight", async () => {
    let active = 0;
    let peak = 0;
    const resolve = vi.fn(async (page: number, retry: number) => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((done) => setTimeout(done, 5));
      active -= 1;
      return resolved(page, retry);
    });
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 8,
      resolve,
      probe: async () => ({ width: 800, height: 1200 }),
    });

    await Promise.all([0, 1, 2, 3, 4, 5].map((index) => source.page(index)));
    expect(resolve).toHaveBeenCalledTimes(6);
    expect(peak).toBeLessThanOrEqual(2);
  });

  it("deduplicates concurrent requests for the same page", async () => {
    const resolve = vi.fn(async (page: number, retry: number) => {
      await new Promise((done) => setTimeout(done, 5));
      return resolved(page, retry);
    });
    const source = new OnlineDirectPageSource({
      gid: GID,
      token: TOKEN,
      pageCount: 4,
      resolve,
      probe: async () => ({ width: 800, height: 1200 }),
    });
    const [a, b] = await Promise.all([source.page(0), source.page(0)]);
    expect(a.url).toBe(b.url);
    expect(resolve).toHaveBeenCalledTimes(1);
  });
});
