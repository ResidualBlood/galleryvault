import { afterEach, describe, expect, it } from "vitest";
import { defineComponent } from "vue";
import { mount } from "@vue/test-utils";
import {
  parseViewModeMap,
  readViewModeMap,
  resolveViewMode,
  useViewMode,
  VIEW_MODE_STORAGE_KEY,
  writeViewModeMap,
  type ViewModeState,
} from "@/composables/useViewMode";

const ALL = ["grid", "list", "table"] as const;

function harness(
  pageKey: string,
  options: { allowed?: readonly ("grid" | "list" | "table")[]; fallback?: "grid" | "list" | "table" } = {},
): ViewModeState {
  let state: ViewModeState | null = null;
  const Host = defineComponent({
    setup() {
      state = useViewMode(pageKey, options);
      return () => null;
    },
  });
  mount(Host);
  if (!state) throw new Error("useViewMode did not initialise");
  return state;
}

function stubMatchMedia(compact: boolean): () => void {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    matches: compact,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

afterEach(() => {
  window.localStorage.clear();
});

describe("parseViewModeMap", () => {
  it("accepts a partial map and drops bad entries", () => {
    expect(parseViewModeMap('{"browse":"list","library":"bogus","x":1}')).toEqual({
      browse: "list",
    });
  });

  it("survives malformed JSON and non-object payloads", () => {
    expect(parseViewModeMap("{not json")).toEqual({});
    expect(parseViewModeMap("[]")).toEqual({});
    expect(parseViewModeMap(null)).toEqual({});
  });
});

describe("resolveViewMode", () => {
  it("uses the stored mode when it is allowed", () => {
    expect(resolveViewMode("table", ALL, "grid", false)).toBe("table");
  });

  it("falls back for unknown or disallowed modes", () => {
    expect(resolveViewMode("nope", ALL, "grid", false)).toBe("grid");
    expect(resolveViewMode("table", ["grid", "list"], "grid", false)).toBe("grid");
  });

  it("temporarily maps table to list on a compact viewport", () => {
    expect(resolveViewMode("table", ALL, "grid", true)).toBe("list");
    expect(resolveViewMode("grid", ALL, "grid", true)).toBe("grid");
  });

  it("keeps the fallback when list is not available", () => {
    expect(resolveViewMode("table", ["grid", "table"], "grid", true)).toBe("grid");
  });
});

describe("useViewMode", () => {
  it("reads a per-page preference and leaves other pages alone", () => {
    writeViewModeMap({ library: "table", browse: "list" });
    expect(readViewModeMap()).toEqual({ library: "table", browse: "list" });

    const browse = harness("browse");
    expect(browse.mode.value).toBe("list");
    expect(browse.stored.value).toBe("list");
  });

  it("writes only its own page key and survives a malformed map", () => {
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, "oops");
    const browse = harness("browse");
    expect(browse.mode.value).toBe("grid");

    browse.setMode("table");
    expect(browse.mode.value).toBe("table");
    expect(readViewModeMap()).toEqual({ browse: "table" });
  });

  it("ignores modes a page does not allow", () => {
    const series = harness("series", { allowed: ["grid", "list"], fallback: "grid" });
    series.setMode("table");
    expect(series.mode.value).toBe("grid");
    expect(readViewModeMap()).toEqual({});
  });

  it("does not overwrite a stored table preference on a compact viewport", () => {
    const restore = stubMatchMedia(true);
    try {
      writeViewModeMap({ browse: "table" });
      const browse = harness("browse");
      expect(browse.isCompact.value).toBe(true);
      expect(browse.mode.value).toBe("list");
      expect(browse.available.value).toEqual(["grid", "list"]);
      expect(readViewModeMap()).toEqual({ browse: "table" });

      browse.setMode("table");
      expect(readViewModeMap()).toEqual({ browse: "table" });
    } finally {
      restore();
    }
  });
});
