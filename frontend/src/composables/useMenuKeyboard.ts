/**
 * Shared WAI-ARIA menu keyboard contract for popover menus.
 *
 * `Home` / `End` jump to the edges, `ArrowUp` / `ArrowDown` move by one and
 * wrap around. The desktop Popover and the context TagMenu both use these
 * helpers; Menu.vue keeps its own copy until it is migrated (out of scope).
 */
export const MENU_ITEM_SELECTOR = '[role="menuitem"]:not(:disabled)';

const NAV_KEYS = new Set(["ArrowDown", "ArrowUp", "Home", "End"]);

/** Enabled menuitems inside a menu root, in DOM order. */
export function menuItems(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return [...root.querySelectorAll<HTMLElement>(MENU_ITEM_SELECTOR)];
}

/** Focus the first enabled item, if the menu has one. */
export function focusFirstMenuItem(root: HTMLElement | null): void {
  menuItems(root)[0]?.focus();
}

export function isMenuNavKey(key: string): boolean {
  return NAV_KEYS.has(key);
}

/**
 * Move focus for one navigation key. Returns `false` when the key is not a
 * navigation key or the menu has no items, so callers know whether to
 * `preventDefault()`.
 */
export function focusMenuItemFor(root: HTMLElement | null, key: string): boolean {
  if (!NAV_KEYS.has(key)) return false;
  const items = menuItems(root);
  if (!items.length) return false;
  const current = items.indexOf(document.activeElement as HTMLElement);
  let next = 0;
  if (key === "End") next = items.length - 1;
  else if (key === "ArrowUp") next = current <= 0 ? items.length - 1 : current - 1;
  else if (key === "ArrowDown") next = current >= items.length - 1 ? 0 : current + 1;
  items[next]?.focus();
  return true;
}
