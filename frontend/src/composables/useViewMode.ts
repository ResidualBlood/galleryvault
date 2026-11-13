import { computed, onBeforeUnmount, onMounted, ref, type Ref } from "vue";
import { COMPACT_VIEWPORT } from "@/stores/library";

/**
 * Per-page grid / list / table preference (PLAN polish §P5, DESIGN C18).
 *
 * Stored as one JSON object under `localStorage.gv_view_mode`:
 *
 *     { "browse": "table", "library": "grid" }
 *
 * The preference is page-scoped (EhViewer's global list/grid setting is
 * deliberately not copied). Below 600px the table view is unavailable: the
 * effective mode falls back to list but the stored value is left untouched, so
 * widening the window brings the table back.
 */
export type ViewMode = "grid" | "list" | "table";

export const VIEW_MODES: readonly ViewMode[] = ["grid", "list", "table"];
export const VIEW_MODE_STORAGE_KEY = "gv_view_mode";

export interface ViewModeOptions {
  /** Modes the page supports, in render order. */
  allowed?: readonly ViewMode[];
  /** Mode used when nothing valid is stored. */
  fallback?: ViewMode;
}

export interface ViewModeState {
  /** Mode actually rendered (narrow screens already resolved to list). */
  mode: Readonly<Ref<ViewMode>>;
  /** Raw stored preference for this page, even when it is temporarily unavailable. */
  stored: Readonly<Ref<ViewMode>>;
  /** Modes currently offerable in the toggle. */
  available: Readonly<Ref<readonly ViewMode[]>>;
  isCompact: Readonly<Ref<boolean>>;
  setMode: (mode: ViewMode) => void;
}

const DEFAULT_ALLOWED: readonly ViewMode[] = VIEW_MODES;

function isViewMode(value: unknown): value is ViewMode {
  return typeof value === "string" && (VIEW_MODES as readonly string[]).includes(value);
}

/** Parse the stored JSON map, ignoring malformed data and unknown modes. */
export function parseViewModeMap(raw: string | null | undefined): Record<string, ViewMode> {
  if (!raw) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {};
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
  const out: Record<string, ViewMode> = {};
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (key && isViewMode(value)) out[key] = value;
  }
  return out;
}

export function readViewModeMap(): Record<string, ViewMode> {
  if (typeof window === "undefined") return {};
  try {
    return parseViewModeMap(window.localStorage.getItem(VIEW_MODE_STORAGE_KEY));
  } catch {
    return {};
  }
}

/** Persist the map; private-mode failures are ignored (default view still works). */
export function writeViewModeMap(map: Record<string, ViewMode>): boolean {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, JSON.stringify(map));
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolve the effective mode from a stored preference.
 *
 * A stored mode outside `allowed` falls back; `table` on a compact viewport
 * temporarily becomes `list` (or the page fallback when list is unsupported).
 */
export function resolveViewMode(
  stored: unknown,
  allowed: readonly ViewMode[] = DEFAULT_ALLOWED,
  fallback: ViewMode = "grid",
  compact = false,
): ViewMode {
  const options = allowed.length ? allowed : DEFAULT_ALLOWED;
  const safeFallback = options.includes(fallback) ? fallback : options[0];
  const candidate = isViewMode(stored) && options.includes(stored) ? stored : safeFallback;
  if (compact && candidate === "table") {
    return options.includes("list") ? "list" : safeFallback;
  }
  return candidate;
}

function readCompact(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(`(max-width: ${COMPACT_VIEWPORT - 1}px)`).matches;
}

export function useViewMode(pageKey: string, options: ViewModeOptions = {}): ViewModeState {
  const allowed = options.allowed?.length ? options.allowed : DEFAULT_ALLOWED;
  const fallback = options.fallback && allowed.includes(options.fallback) ? options.fallback : allowed[0];

  const stored = ref<ViewMode>(
    resolveViewMode(readViewModeMap()[pageKey], allowed, fallback, false),
  );
  const isCompact = ref(readCompact());
  let media: MediaQueryList | null = null;

  const mode = computed(() =>
    resolveViewMode(stored.value, allowed, fallback, isCompact.value),
  );

  const available = computed(() =>
    isCompact.value ? allowed.filter((entry) => entry !== "table") : allowed,
  );

  function setMode(next: ViewMode): void {
    if (!allowed.includes(next)) return;
    // Narrow screens cannot render the table; ignore the request instead of
    // writing an unreachable preference.
    if (isCompact.value && next === "table") return;
    stored.value = next;
    const map = readViewModeMap();
    map[pageKey] = next;
    writeViewModeMap(map);
  }

  function onMediaChange(event: MediaQueryListEvent): void {
    isCompact.value = event.matches;
  }

  onMounted(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    media = window.matchMedia(`(max-width: ${COMPACT_VIEWPORT - 1}px)`);
    isCompact.value = media.matches;
    media.addEventListener?.("change", onMediaChange);
  });

  onBeforeUnmount(() => {
    media?.removeEventListener?.("change", onMediaChange);
  });

  return {
    mode,
    stored,
    available,
    isCompact,
    setMode,
  };
}
