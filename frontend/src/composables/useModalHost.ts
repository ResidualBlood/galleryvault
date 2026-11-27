import { ref, type Ref } from "vue";

/** Attribute every open native modal sets on its `<dialog>` element. */
export const MODAL_ATTR = "data-gv-modal";

/** The element a nested overlay should teleport into: the deepest open modal,
 *  or `null` when the page is not modal. */
export function findModalHost(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  const open = document.querySelectorAll<HTMLElement>(`[${MODAL_ATTR}]`);
  return open.length ? (open[open.length - 1] ?? null) : null;
}

export interface ModalHost {
  /** Teleport `to` target; `"body"` is the safe non-modal fallback. */
  host: Ref<string | HTMLElement>;
  /** Re-read the deepest open modal (call when the overlay opens). */
  refresh: () => void;
  /** Return to body (call after the overlay leaves the DOM). */
  reset: () => void;
}

/**
 * Shared Teleport target for overlays that must stay interactive while a
 * native modal is open. A modal makes the rest of `<body>` inert, so a nested
 * overlay teleported to body would be unclickable and sit under the top layer;
 * teleporting it into the open `<dialog>` keeps it in the modal's subtree.
 */
export function useModalHost(): ModalHost {
  const host = ref<string | HTMLElement>(findModalHost() ?? "body");

  function refresh(): void {
    host.value = findModalHost() ?? "body";
  }

  function reset(): void {
    host.value = "body";
  }

  return { host, refresh, reset };
}
