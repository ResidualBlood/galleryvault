/**
 * In-page GM shim for the companion userscript E2E.
 *
 * Real extension behaviour emulated here:
 *  - `GM_getValue` / `GM_setValue` (sync, persisted in localStorage per page);
 *  - `GM_xmlhttpRequest` running outside the page (no CORS, no page cookies):
 *    the request is forwarded to the Node-side binding registered with
 *    `page.exposeFunction("__gvGmRequest", ...)`.
 *
 * The function is serialized by Playwright, so it must stay self-contained.
 */
export interface GmShimOptions {
  base: string;
  token: string;
  /** Seed `GM_setValue` with base + token, otherwise the panel asks for them. */
  configured: boolean;
}

export function installGmShim(options: GmShimOptions): void {
  const win = window as unknown as Record<string, unknown>;
  const storageKey = (name: string) => `gm:${name}`;

  if (options.configured) {
    try {
      window.localStorage.setItem(storageKey("gv_base_url"), JSON.stringify(options.base));
      window.localStorage.setItem(storageKey("gv_api_token"), JSON.stringify(options.token));
    } catch {
      /* ignore quota / opaque origin */
    }
  }

  win.GM_getValue = (name: string, fallback?: unknown) => {
    try {
      const raw = window.localStorage.getItem(storageKey(name));
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  };

  win.GM_setValue = (name: string, value: unknown) => {
    try {
      window.localStorage.setItem(storageKey(name), JSON.stringify(value));
    } catch {
      /* ignore */
    }
  };

  const calls: Array<{ method: string; url: string; headers: Record<string, string>; data?: string }> = [];
  win.__gvGmRequests = calls;

  win.GM_xmlhttpRequest = (details: {
    method?: string;
    url: string;
    headers?: Record<string, string>;
    data?: string;
    onload?: (response: { status: number; responseText: string }) => void;
    onerror?: (error: unknown) => void;
  }) => {
    const entry = {
      method: details.method || "GET",
      url: details.url,
      headers: details.headers || {},
      data: details.data,
    };
    calls.push(entry);
    const binding = win.__gvGmRequest as
      | ((request: typeof entry) => Promise<{ status: number; responseText: string }>)
      | undefined;
    if (typeof binding !== "function") {
      details.onerror?.({ error: "binding unavailable" });
      return;
    }
    binding(entry)
      .then((response) => details.onload?.(response))
      .catch((error) => details.onerror?.(error));
  };
}
