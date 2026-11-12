/**
 * Per-device online image mode (`gv_online_image_mode`, PLAN §4.2).
 *
 * - `direct` (default): the backend only resolves the page; the browser fetches
 *   the H@H image itself, so no server image budget is spent.
 * - `proxy`: the fallback through the backend image proxy, for devices that
 *   cannot reach H@H nodes.
 *
 * The spike that could have flipped the default to `proxy` was not produced, so
 * the documented default (`direct`) stays. The choice is per device and never
 * leaves localStorage.
 */
export const ONLINE_IMAGE_MODE_KEY = "gv_online_image_mode";

export type OnlineImageMode = "direct" | "proxy";

export const ONLINE_IMAGE_MODES: readonly OnlineImageMode[] = ["direct", "proxy"];

export const DEFAULT_ONLINE_IMAGE_MODE: OnlineImageMode = "direct";

export function isOnlineImageMode(value: unknown): value is OnlineImageMode {
  return (
    typeof value === "string" &&
    (ONLINE_IMAGE_MODES as readonly string[]).includes(value)
  );
}

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

export function readOnlineImageMode(target: Storage | null = storage()): OnlineImageMode {
  try {
    const stored = target?.getItem(ONLINE_IMAGE_MODE_KEY) ?? null;
    return isOnlineImageMode(stored) ? stored : DEFAULT_ONLINE_IMAGE_MODE;
  } catch {
    return DEFAULT_ONLINE_IMAGE_MODE;
  }
}

export function writeOnlineImageMode(
  mode: OnlineImageMode,
  target: Storage | null = storage(),
): OnlineImageMode {
  const safe = isOnlineImageMode(mode) ? mode : DEFAULT_ONLINE_IMAGE_MODE;
  try {
    target?.setItem(ONLINE_IMAGE_MODE_KEY, safe);
  } catch {
    /* private mode / blocked storage: the in-memory mode still applies */
  }
  return safe;
}
