/**
 * Unit tests for the GalleryVault companion userscript.
 *
 * Run: `npm --prefix frontend/next run test:unit -- userscript`
 *
 * The pure helpers are imported straight from `companion.mjs` (the source of
 * truth of the built file), and the generated userscript is checked for drift,
 * so the tests exercise the shipped code rather than a copy.
 */
/* eslint-disable no-restricted-syntax -- the userscript and its fixtures talk to the standalone API surface, not the SPA client */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  EMPTY_STATUS,
  buildApiRequest,
  createCompanion,
  downloadAccepted,
  favoriteSucceeded,
  galleryVaultUrl,
  init,
  isUnauthorized,
  mergeStatus,
  normalizeBaseUrl,
  normalizeDownloadStatus,
  parseGalleryLocation,
  readSettings,
  safeJsonParse,
  statusChips,
  statusPath,
} from "./companion.mjs";
import { renderUserScript } from "./build.mjs";

const PROJECT_ROOT = process.cwd();
const COMPANION_SOURCE = readFileSync(resolve(PROJECT_ROOT, "userscript/companion.mjs"), "utf8");
const BUILT_SCRIPT = readFileSync(
  resolve(PROJECT_ROOT, "public/galleryvault-companion.user.js"),
  "utf8",
);

const GID = 1526342;
const EH_TOKEN = "0123abcd45";
const API_TOKEN = "tok-secret-9f8e7d6c";

/* ------------------------------------------------------------------ metadata */

describe("built userscript", () => {
  it("is the current build of companion.mjs", () => {
    expect(renderUserScript(COMPANION_SOURCE)).toBe(BUILT_SCRIPT);
  });

  it("matches only the two EH gallery hosts", () => {
    const matches = BUILT_SCRIPT.match(/^\/\/ @match\s+(\S+)/gm) ?? [];
    expect(matches).toEqual([
      "// @match        https://e-hentai.org/g/*",
      "// @match        https://exhentai.org/g/*",
    ]);
    expect(BUILT_SCRIPT).not.toMatch(/@match\s+\*:\/\//);
  });

  it("grants only the GM APIs the panel needs", () => {
    const grants = BUILT_SCRIPT.match(/^\/\/ @grant\s+(\S+)/gm) ?? [];
    expect(grants).toEqual([
      "// @grant        GM_xmlhttpRequest",
      "// @grant        GM_getValue",
      "// @grant        GM_setValue",
    ]);
  });

  it("never references EH session cookies", () => {
    expect(BUILT_SCRIPT).not.toMatch(/document\.cookie|ipb_|igneous/i);
  });
});

/* ----------------------------------------------------------------- pure logic */

describe("parseGalleryLocation", () => {
  it("reads gid and token from a gallery path", () => {
    expect(parseGalleryLocation({ pathname: `/g/${GID}/${EH_TOKEN}/` })).toEqual({
      gid: GID,
      token: EH_TOKEN,
    });
  });

  it("accepts a full href and deep page paths", () => {
    expect(parseGalleryLocation(`https://exhentai.org/g/${GID}/${EH_TOKEN}/5/`)).toEqual({
      gid: GID,
      token: EH_TOKEN,
    });
  });

  it("tolerates a missing trailing slash", () => {
    expect(parseGalleryLocation(`/g/${GID}/${EH_TOKEN}`)).toEqual({
      gid: GID,
      token: EH_TOKEN,
    });
  });

  it("rejects non-gallery pages", () => {
    expect(parseGalleryLocation({ pathname: "/" })).toBeNull();
    expect(parseGalleryLocation({ pathname: "/s/0123abcd45/123-1" })).toBeNull();
    expect(parseGalleryLocation({ pathname: `/g/${GID}` })).toBeNull();
    expect(parseGalleryLocation({ pathname: "/g/abc/def/" })).toBeNull();
    expect(parseGalleryLocation("")).toBeNull();
    expect(parseGalleryLocation(undefined)).toBeNull();
  });
});

describe("normalizeBaseUrl", () => {
  it("keeps origin + path and drops trailing slashes", () => {
    expect(normalizeBaseUrl(" http://192.168.1.10:8200/ ")).toBe("http://192.168.1.10:8200");
    expect(normalizeBaseUrl("https://gv.example.com/app/")).toBe("https://gv.example.com/app");
  });

  it("rejects empty, relative and non-http values", () => {
    expect(normalizeBaseUrl("")).toBe("");
    expect(normalizeBaseUrl("192.168.1.10:8200")).toBe("");
    expect(normalizeBaseUrl("javascript:alert(1)")).toBe("");
    expect(normalizeBaseUrl(null)).toBe("");
  });
});

describe("buildApiRequest", () => {
  it("sends the API token as an Authorization Bearer header", () => {
    const request = buildApiRequest(`http://127.0.0.1:8201/`, API_TOKEN, {
      method: "get",
      path: statusPath([GID]),
    });
    expect(request.method).toBe("GET");
    expect(request.url).toBe(`http://127.0.0.1:8201/api/eh/status?gids=${GID}`);
    expect(request.headers.Authorization).toBe(`Bearer ${API_TOKEN}`);
    expect(request.data).toBeUndefined();
  });

  it("encodes JSON bodies and keeps the bearer header", () => {
    const request = buildApiRequest("http://gv.local:8200", API_TOKEN, {
      method: "POST",
      path: "/api/downloads",
      body: { gid: GID, token: EH_TOKEN, quality: "original" },
    });
    expect(request.headers.Authorization).toBe(`Bearer ${API_TOKEN}`);
    expect(request.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(request.data)).toEqual({
      gid: GID,
      token: EH_TOKEN,
      quality: "original",
    });
  });

  it("refuses to build a request without configuration or token", () => {
    expect(() => buildApiRequest("", API_TOKEN, { path: "/api/x" })).toThrow("invalid_base_url");
    expect(() => buildApiRequest("http://gv.local", "", { path: "/api/x" })).toThrow("missing_token");
  });

  it("keeps the token out of thrown messages", () => {
    try {
      buildApiRequest("not a url", API_TOKEN, { path: "/api/x" });
      expect.unreachable("expected a throw");
    } catch (error) {
      expect(String((error as Error).message)).not.toContain(API_TOKEN);
    }
  });
});

describe("statusPath", () => {
  it("joins up to 100 numeric gids", () => {
    expect(statusPath([1, 2, 3])).toBe("/api/eh/status?gids=1,2,3");
    expect(statusPath(42)).toBe("/api/eh/status?gids=42");
    expect(statusPath([])).toBe("/api/eh/status?gids=");
  });

  it("drops invalid gids", () => {
    expect(statusPath([1, 0, -3, 2.5, "7"])).toBe("/api/eh/status?gids=1,7");
  });
});

describe("mergeStatus", () => {
  it("maps backend snake_case onto the view model", () => {
    const merged = mergeStatus(EMPTY_STATUS, {
      gid: GID,
      in_library: true,
      gallery_id: 42,
      favorited: true,
      favcat: 2,
      download_status: "downloading",
    });
    expect(merged).toEqual({
      inLibrary: true,
      galleryId: 42,
      favorited: true,
      favcat: 2,
      downloadStatus: "downloading",
    });
  });

  it("keeps previous values for a partial item", () => {
    const previous = {
      inLibrary: true,
      galleryId: 42,
      favorited: true,
      favcat: 3,
      downloadStatus: "downloading",
    };
    expect(mergeStatus(previous, { gid: GID })).toEqual(previous);
    expect(mergeStatus(previous, null)).toEqual(previous);
  });

  it("clears badges when the backend says so", () => {
    const merged = mergeStatus({ ...EMPTY_STATUS, inLibrary: true, favorited: true, favcat: 1 }, {
      in_library: false,
      favorited: false,
      favcat: null,
      download_status: null,
    });
    expect(merged.inLibrary).toBe(false);
    expect(merged.favorited).toBe(false);
    expect(merged.favcat).toBeNull();
    expect(merged.downloadStatus).toBeNull();
  });

  it("rejects out-of-range favcat values", () => {
    expect(mergeStatus(EMPTY_STATUS, { favcat: 12 }).favcat).toBeNull();
    expect(mergeStatus(EMPTY_STATUS, { favcat: -1 }).favcat).toBeNull();
  });
});

describe("statusChips", () => {
  it("labels library, favourite and download state", () => {
    const chips = statusChips({
      inLibrary: true,
      favorited: true,
      favcat: 2,
      downloadStatus: "downloading",
    });
    expect(chips.map((chip) => chip.label)).toEqual(["已在库", "已收藏（分类 2）", "下载中"]);
    expect(chips.map((chip) => chip.key)).toEqual(["library", "favorite", "download"]);
  });

  it("shows muted placeholders for a fresh gallery", () => {
    expect(statusChips(EMPTY_STATUS).map((chip) => chip.label)).toEqual(["不在库", "未收藏"]);
  });

  it("does not repeat a completed download badge", () => {
    const labels = statusChips({ inLibrary: true, downloadStatus: "success" }).map(
      (chip) => chip.label,
    );
    expect(labels).not.toContain("已下载");
  });

  it("marks a failed download", () => {
    const chip = statusChips({ downloadStatus: "failed" }).find((c) => c.key === "download");
    expect(chip).toMatchObject({ label: "下载失败", tone: "bad" });
  });
});

describe("response helpers", () => {
  it("detects 401 and cloud-first favourite success", () => {
    expect(isUnauthorized({ status: 401 })).toBe(true);
    expect(isUnauthorized({ status: 200 })).toBe(false);
    expect(favoriteSucceeded({ successful_gids: [GID] }, GID)).toBe(true);
    expect(favoriteSucceeded({ successful_gids: [], cloud_ok: false }, GID)).toBe(false);
    expect(favoriteSucceeded(null, GID)).toBe(false);
  });

  it("requires a download id in the accepted response", () => {
    expect(downloadAccepted({ id: 7, status: "pending" })).toBe(true);
    expect(downloadAccepted({ status: "pending" })).toBe(false);
    expect(downloadAccepted(null)).toBe(false);
  });

  it("parses JSON defensively and normalises statuses", () => {
    expect(safeJsonParse('{"a":1}')).toEqual({ a: 1 });
    expect(safeJsonParse("<html>")).toBeNull();
    expect(normalizeDownloadStatus(" Downloading ")).toBe("downloading");
    expect(normalizeDownloadStatus(undefined)).toBeNull();
  });

  it("builds the in-app online detail link", () => {
    expect(galleryVaultUrl("http://gv.local:8200/", GID, EH_TOKEN)).toBe(
      `http://gv.local:8200/#/online/g/${GID}/${EH_TOKEN}`,
    );
    expect(galleryVaultUrl("", GID, EH_TOKEN)).toBe("");
  });
});

/* ------------------------------------------------------------------- the panel */

interface FakeCall {
  method: string;
  url: string;
  headers: Record<string, string>;
  data?: string;
}

function memoryStore(initial: Record<string, unknown> = {}) {
  const values = new Map<string, unknown>(Object.entries(initial));
  return {
    values,
    get: (key: string, fallback: unknown) => (values.has(key) ? values.get(key) : fallback),
    set: (key: string, value: unknown) => {
      values.set(key, value);
    },
  };
}

function setupPanel(options: {
  configured?: boolean;
  status?: number;
  bodies?: Record<string, unknown>;
  statusItem?: Record<string, unknown>;
}) {
  document.head.innerHTML = "";
  document.body.innerHTML = '<div id="gdd"><div id="gd5">Download</div></div>';
  const calls: FakeCall[] = [];
  const store = memoryStore(
    options.configured === false
      ? {}
      : { gv_base_url: "http://127.0.0.1:8201", gv_api_token: API_TOKEN },
  );
  const request = async (request: FakeCall) => {
    calls.push(request);
    const path = request.url.replace("http://127.0.0.1:8201", "");
    if (options.status && options.status >= 400) {
      return { status: options.status, responseText: '{"detail":"unauthorized"}' };
    }
    if (path.startsWith("/api/eh/status")) {
      return {
        status: 200,
        responseText: JSON.stringify({
          items: [
            {
              gid: GID,
              in_library: true,
              gallery_id: 42,
              favorited: false,
              favcat: null,
              download_status: null,
              ...(options.statusItem || {}),
            },
          ],
        }),
      };
    }
    if (path.startsWith("/api/favorites/categories")) {
      return {
        status: 200,
        responseText: JSON.stringify([{ favcat: 2, name: "Doujinshi" }]),
      };
    }
    if (path.startsWith("/api/downloads")) {
      return {
        status: 200,
        responseText: JSON.stringify({
          id: 7,
          gid: GID,
          status: "pending",
          ...(options.bodies?.downloads || {}),
        }),
      };
    }
    if (path.startsWith("/api/favorites/add")) {
      return {
        status: 200,
        responseText: JSON.stringify({
          cloud_ok: true,
          cloud_failed: [],
          successful_gids: [GID],
        }),
      };
    }
    return { status: 404, responseText: "{}" };
  };
  const companion = createCompanion({
    doc: document,
    location: { pathname: `/g/${GID}/${EH_TOKEN}/` },
    store,
    request,
  });
  return { companion: companion!, calls, store };
}

describe("companion panel", () => {
  it("mounts next to the download row and shows backend status", async () => {
    const { companion } = setupPanel({});
    companion.mount();
    await companion.refresh();
    const panel = document.getElementById("gv-companion-panel")!;
    expect(panel).not.toBeNull();
    expect(panel.textContent).toContain("已在库");
    expect(panel.textContent).toContain("未收藏");
    expect(panel.textContent).toContain("下载到 GalleryVault");
    expect(panel.textContent).toContain("收藏到 GalleryVault");
    const link = panel.querySelector('[data-action="open"]') as HTMLAnchorElement;
    expect(link.href).toBe(`http://127.0.0.1:8201/#/online/g/${GID}/${EH_TOKEN}`);
    // The favcat picker starts on the gallery's current category.
    expect((panel.querySelector('[data-role="favcat"]') as HTMLSelectElement).value).toBe("0");
  });

  it("preselects the gallery's current favcat", async () => {
    const { companion } = setupPanel({ statusItem: { favorited: true, favcat: 5 } });
    companion.mount();
    await companion.refresh();
    const panel = document.getElementById("gv-companion-panel")!;
    expect((panel.querySelector('[data-role="favcat"]') as HTMLSelectElement).value).toBe("5");
    expect(panel.textContent).toContain("已收藏（分类 5）");
  });

  it("posts a download with the chosen quality and a bearer header", async () => {
    const { companion, calls } = setupPanel({});
    companion.mount();
    await companion.refresh();
    const panel = document.getElementById("gv-companion-panel")!;
    const quality = panel.querySelector('[data-role="quality"]') as HTMLSelectElement;
    quality.value = "original";
    quality.dispatchEvent(new Event("change"));
    (panel.querySelector('[data-action="download"]') as HTMLButtonElement).click();

    await vi.waitFor(() => {
      expect(calls.some((call) => call.url.endsWith("/api/downloads"))).toBe(true);
    });
    const download = calls.find((call) => call.url.endsWith("/api/downloads"))!;
    expect(download.method).toBe("POST");
    expect(download.headers.Authorization).toBe(`Bearer ${API_TOKEN}`);
    expect(JSON.parse(download.data!)).toEqual({
      gid: GID,
      token: EH_TOKEN,
      quality: "original",
    });
    await vi.waitFor(() => {
      expect(document.getElementById("gv-companion-panel")!.textContent).toContain("已加入");
    });
  });

  it("favorites into the selected favcat and only trusts the cloud result", async () => {
    const { companion, calls } = setupPanel({});
    companion.mount();
    await companion.refresh();
    const panel = document.getElementById("gv-companion-panel")!;
    const favcat = panel.querySelector('[data-role="favcat"]') as HTMLSelectElement;
    favcat.value = "2";
    favcat.dispatchEvent(new Event("change"));
    (panel.querySelector('[data-action="favorite"]') as HTMLButtonElement).click();

    await vi.waitFor(() => {
      expect(calls.some((call) => call.url.endsWith("/api/favorites/add"))).toBe(true);
    });
    const favorite = calls.find((call) => call.url.endsWith("/api/favorites/add"))!;
    expect(favorite.headers.Authorization).toBe(`Bearer ${API_TOKEN}`);
    expect(JSON.parse(favorite.data!).target_favcat).toBe(2);
    await vi.waitFor(() => {
      expect(document.getElementById("gv-companion-panel")!.textContent).toContain(
        "已收藏（分类 2）",
      );
    });
  });

  it("guides first-time users through configuration", async () => {
    const { companion, store } = setupPanel({ configured: false });
    companion.mount();
    await companion.refresh();
    const panel = document.getElementById("gv-companion-panel")!;
    expect(panel.querySelector('[data-role="base"]')).not.toBeNull();
    expect(panel.querySelector('[data-role="token"]')).not.toBeNull();
    expect(panel.textContent).toContain("首次使用");

    (panel.querySelector('[data-role="base"]') as HTMLInputElement).value =
      "http://127.0.0.1:8201";
    (panel.querySelector('[data-role="token"]') as HTMLInputElement).value = API_TOKEN;
    (panel.querySelector('[data-action="save"]') as HTMLButtonElement).click();
    await vi.waitFor(() => {
      expect(store.values.get("gv_api_token")).toBe(API_TOKEN);
      expect(document.getElementById("gv-companion-panel")!.textContent).toContain("已在库");
    });
  });

  it("asks for a new token on 401", async () => {
    const { companion } = setupPanel({ status: 401 });
    companion.mount();
    await companion.refresh();
    const panel = document.getElementById("gv-companion-panel")!;
    expect(panel.dataset.state).toBe("unauthorized");
    expect(panel.textContent).toContain("重新配置");
    expect(panel.querySelector('[data-role="token"]')).not.toBeNull();
    expect(panel.querySelector('[data-action="download"]')).toBeNull();
  });

  it("never writes the API token into the DOM or the console", async () => {
    const spies = [
      vi.spyOn(console, "log"),
      vi.spyOn(console, "warn"),
      vi.spyOn(console, "error"),
      vi.spyOn(console, "info"),
      vi.spyOn(console, "debug"),
    ];
    const { companion } = setupPanel({});
    companion.mount();
    await companion.refresh();
    (document.querySelector('[data-action="download"]') as HTMLButtonElement).click();
    await vi.waitFor(() => {
      expect(document.getElementById("gv-companion-panel")!.textContent).toContain("已加入");
    });
    expect(document.body.innerHTML).not.toContain(API_TOKEN);
    const logged = spies.flatMap((spy) => spy.mock.calls.flat()).map((value) => String(value));
    expect(logged.some((line) => line.includes(API_TOKEN))).toBe(false);
  });

  it("does nothing outside gallery pages and tolerates a missing entry point", () => {
    document.head.innerHTML = "";
    document.body.innerHTML = "";
    expect(
      createCompanion({
        doc: document,
        location: { pathname: "/s/0123abcd45/123-1" },
        store: memoryStore(),
        request: async () => ({ status: 200, responseText: "{}" }),
      }),
    ).toBeNull();
    expect(
      createCompanion({
        doc: document,
        location: { pathname: `/g/${GID}/${EH_TOKEN}/` },
        store: memoryStore(),
        request: async () => ({ status: 200, responseText: "{}" }),
      })?.mount(),
    ).not.toBeNull();
  });

  it("reads persisted settings through the GM store", () => {
    const store = memoryStore({ gv_base_url: "http://gv.local:8200/", gv_api_token: "abc" });
    expect(readSettings(store)).toEqual({ base: "http://gv.local:8200", token: "abc" });
    expect(init).toBeTypeOf("function");
  });
});
