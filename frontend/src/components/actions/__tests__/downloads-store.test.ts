import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { downloadsEp } from "@/api/downloads";
import { ehStatusEp } from "@/api/eh";
import {
  DOWNLOAD_ACTIVE_POLL_MS,
  DOWNLOAD_IDLE_POLL_MS,
  useDownloadsStore,
} from "@/stores/downloads";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const ORIGINAL_VISIBILITY = Object.getOwnPropertyDescriptor(Document.prototype, "visibilityState");

function setVisibility(hidden: boolean): void {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => (hidden ? "hidden" : "visible"),
  });
}

function statusItem(mode: "pending" | "success") {
  return {
    gid: 7,
    in_library: mode === "success",
    gallery_id: mode === "success" ? 70 : null,
    favorited: false,
    favcat: null,
    download_status: mode === "success" ? "success" : "pending",
  };
}

describe("downloads store", () => {
  let mode: "pending" | "success";
  let statusCalls: number;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setActivePinia(createPinia());
    mode = "pending";
    statusCalls = 0;
    setVisibility(false);
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === ehStatusEp.path) {
        statusCalls += 1;
        return jsonResponse({ items: [statusItem(mode)] });
      }
      if (url.pathname === downloadsEp.path) {
        return jsonResponse({ total: 0, page: 1, page_size: 500, items: [] });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    useDownloadsStore().stop();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    if (ORIGINAL_VISIBILITY) {
      Object.defineProperty(Document.prototype, "visibilityState", ORIGINAL_VISIBILITY);
    }
  });

  it("polls every 2s while active and every 10s when idle", async () => {
    vi.useFakeTimers();
    const store = useDownloadsStore();

    store.watch(7);
    await vi.advanceTimersByTimeAsync(0);
    expect(statusCalls).toBe(1);
    expect(store.nextInterval()).toBe(DOWNLOAD_ACTIVE_POLL_MS);

    await vi.advanceTimersByTimeAsync(DOWNLOAD_ACTIVE_POLL_MS);
    expect(statusCalls).toBe(2);
    expect(store.hasActive()).toBe(true);

    mode = "success";
    await vi.advanceTimersByTimeAsync(DOWNLOAD_ACTIVE_POLL_MS);
    expect(statusCalls).toBe(3);
    expect(store.hasActive()).toBe(false);
    expect(store.nextInterval()).toBe(DOWNLOAD_IDLE_POLL_MS);

    await vi.advanceTimersByTimeAsync(DOWNLOAD_IDLE_POLL_MS - 1);
    expect(statusCalls).toBe(3);
    await vi.advanceTimersByTimeAsync(1);
    expect(statusCalls).toBe(4);
  });

  it("pauses polling while the document is hidden and resumes on visibility", async () => {
    vi.useFakeTimers();
    const store = useDownloadsStore();
    store.watch(7);
    await vi.advanceTimersByTimeAsync(0);
    expect(statusCalls).toBe(1);

    setVisibility(true);
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(statusCalls).toBe(1);

    setVisibility(false);
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(statusCalls).toBe(2);
  });

  it("marks the gid queued after POST /api/downloads and sends the chosen quality", async () => {
    const store = useDownloadsStore();
    fetchMock.mockImplementationOnce(async () =>
      jsonResponse({ id: 9, gid: 7, title: "T", status: "pending" }, 202),
    );

    const queued = await store.enqueue(7, "token-7", { quality: "original" });

    expect(queued).toBe(true);
    expect(store.get(7).status).toBe("queued");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      gid: 7,
      token: "token-7",
      quality: "original",
    });
  });

  it("does not enqueue a second request while one is active", async () => {
    const store = useDownloadsStore();
    store.applySeed(7, { status: "downloading" });
    fetchMock.mockClear();

    const queued = await store.enqueue(7, "token-7");

    expect(queued).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
