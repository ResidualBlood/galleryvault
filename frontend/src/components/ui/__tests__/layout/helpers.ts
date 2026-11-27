import { vi } from "vitest";
import { i18n } from "@/i18n";

/** Mount options that install the shared i18n instance. */
export const globalPlugins = { plugins: [i18n] };

interface MediaStub {
  matches: boolean;
  media: string;
  onchange: null;
  addEventListener: () => void;
  removeEventListener: () => void;
  addListener: () => void;
  removeListener: () => void;
  dispatchEvent: () => boolean;
}

/**
 * Replace `window.matchMedia` so layout components resolve a deterministic
 * wide / compact breakpoint in jsdom.
 */
export function stubMatchMedia(wide: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(
      (query: string): MediaStub => ({
        matches: wide,
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }),
    ),
  );
}
