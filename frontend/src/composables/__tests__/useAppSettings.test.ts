import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchSettings } from "@/api/settings";
import {
  ensureAppSettings,
  peekAppSettings,
  resetAppSettingsCache,
} from "@/composables/useAppSettings";

vi.mock("@/api/settings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/settings")>();
  return { ...actual, fetchSettings: vi.fn() };
});

const mockedFetch = vi.mocked(fetchSettings);

describe("useAppSettings cache", () => {
  beforeEach(() => {
    resetAppSettingsCache();
    mockedFetch.mockReset();
  });

  it("reads GET /api/settings once and serves the cached value afterwards", async () => {
    mockedFetch.mockResolvedValue({ favorites_cloud_open: "external" });

    const first = await ensureAppSettings();
    const second = await ensureAppSettings();

    expect(first).toEqual({ favorites_cloud_open: "external" });
    expect(second).toBe(first);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(peekAppSettings()).toBe(first);
  });

  it("refreshes on demand while keeping the previous value usable", async () => {
    mockedFetch.mockResolvedValueOnce({ favorites_cloud_open: "app" });
    const stale = await ensureAppSettings();
    expect(peekAppSettings()).toEqual({ favorites_cloud_open: "app" });

    let release: (value: Record<string, unknown>) => void = () => {};
    mockedFetch.mockReturnValueOnce(
      new Promise((resolve) => {
        release = resolve;
      }),
    );

    const refresh = ensureAppSettings(true);
    expect(peekAppSettings()).toBe(stale);
    release({ favorites_cloud_open: "external" });
    await refresh;

    expect(peekAppSettings()).toEqual({ favorites_cloud_open: "external" });
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it("keeps the cache empty when the read fails, so callers use defaults", async () => {
    mockedFetch.mockRejectedValue(new Error("offline"));

    await expect(ensureAppSettings()).resolves.toBeNull();
    expect(peekAppSettings()).toBeNull();
  });
});
