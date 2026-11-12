import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ep, getCsrfToken, request, setUnauthorizedHandler } from "./client";

function jsonResponse(data: unknown, status = 200): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client", () => {
  beforeEach(() => {
    document.cookie = "galleryvault_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
  });

  it("sends cookies and the CSRF header on writes, and JSON bodies", async () => {
    document.cookie = "galleryvault_csrf=csrf-token-42";
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await request(ep("POST", "/api/settings"), { body: { paused: true } });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/settings");
    expect(init.credentials).toBe("include");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-token-42");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ paused: true }));
  });

  it("omits the CSRF header when the cookie is absent", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(null, 204));
    vi.stubGlobal("fetch", fetchMock);

    await request(ep("DELETE", "/api/downloads/1"));
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("returns null for 204 and exposes HTTP errors with detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "nope" }, 500)));
    await expect(request(ep("GET", "/api/pause"))).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "nope",
      detail: "nope",
    });
  });

  it("calls the unauthorized handler on 401 and still rejects", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "auth" }, 401)));

    await expect(request(ep("GET", "/api/settings"))).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("skips the unauthorized handler for the session probe", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "auth" }, 401)));

    await expect(
      request(ep("GET", "/api/auth/session"), { skipAuthRedirect: true }),
    ).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("aborts a request after the default/custom timeout", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const pending = request(ep("GET", "/api/pause"), { timeoutMs: 25 });
    const assertion = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(30);
    await assertion;
    vi.useRealTimers();
  });

  it("forwards an external AbortSignal", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const pending = request(ep("GET", "/api/pause"), { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("reads the CSRF cookie with URL decoding", () => {
    document.cookie = "galleryvault_csrf=a%20b";
    expect(getCsrfToken()).toBe("a b");
  });
});
