/**
 * Visibility-aware polling.
 *
 * The legacy downloads page used `setInterval` and returned early when
 * `document.hidden`; this keeps the same behaviour but also refreshes
 * immediately when the tab becomes visible again. Hidden tabs issue no
 * requests at all (PLAN §1.3, acceptance b6).
 */

export interface VisibilitySource {
  readonly visibilityState?: DocumentVisibilityState;
  readonly hidden?: boolean;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

export function isPageHidden(source: VisibilitySource): boolean {
  return source.hidden === true || source.visibilityState === "hidden";
}

export interface VisiblePoller {
  stop: () => void;
  /** Runs one tick now if the page is visible (used by tests). */
  tick: () => void;
}

export function startVisiblePolling(
  callback: () => void,
  intervalMs: number,
  source: VisibilitySource = document,
): VisiblePoller {
  let disposed = false;

  const tick = (): void => {
    if (disposed) return;
    if (!isPageHidden(source)) callback();
  };

  tick();
  const timer = setInterval(tick, intervalMs);

  const onVisibilityChange = (): void => {
    if (!isPageHidden(source)) tick();
  };
  source.addEventListener("visibilitychange", onVisibilityChange);

  return {
    tick,
    stop: () => {
      if (disposed) return;
      disposed = true;
      clearInterval(timer);
      source.removeEventListener("visibilitychange", onVisibilityChange);
    },
  };
}
