import { ref } from "vue";
import { defineStore } from "pinia";

export interface ToastMessage {
  id: number;
  text: string;
  kind: "info" | "success" | "error";
}

/** Why a toast's auto-dismiss timer is paused. */
export type ToastPauseReason = "pointer" | "focus";

const TOAST_TTL_MS = 4000;

interface ToastTimer {
  handle: number | null;
  deadline: number;
  remaining: number;
  pausedBy: Set<ToastPauseReason>;
}

export const useUiStore = defineStore("ui", () => {
  const toasts = ref<ToastMessage[]>([]);
  const timers = new Map<number, ToastTimer>();
  /** Element focused when the toast was pushed, used to restore focus. */
  const returnFocus = new Map<number, HTMLElement | null>();
  let nextId = 1;

  function clearTimer(timer: ToastTimer): void {
    if (timer.handle !== null) {
      window.clearTimeout(timer.handle);
      timer.handle = null;
    }
  }

  function arm(id: number, timer: ToastTimer, ms: number): void {
    timer.remaining = ms;
    timer.deadline = Date.now() + ms;
    timer.handle = window.setTimeout(() => dismiss(id), ms);
  }

  function dismiss(id: number): void {
    const timer = timers.get(id);
    if (timer) {
      clearTimer(timer);
      timers.delete(id);
    }
    returnFocus.delete(id);
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  function push(text: string, kind: ToastMessage["kind"] = "info"): number {
    const id = nextId++;
    toasts.value = [...toasts.value, { id, text, kind }];
    if (typeof window !== "undefined") {
      returnFocus.set(
        id,
        typeof document !== "undefined" && document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null,
      );
      const timer: ToastTimer = {
        handle: null,
        deadline: 0,
        remaining: TOAST_TTL_MS,
        pausedBy: new Set(),
      };
      timers.set(id, timer);
      arm(id, timer, TOAST_TTL_MS);
    }
    return id;
  }

  /** Pause auto-dismiss while the pointer or keyboard focus is on a toast. */
  function pauseToast(id: number, reason: ToastPauseReason): void {
    const timer = timers.get(id);
    if (!timer || timer.pausedBy.has(reason)) return;
    timer.pausedBy.add(reason);
    if (timer.pausedBy.size === 1) {
      timer.remaining = Math.max(0, timer.deadline - Date.now());
      clearTimer(timer);
    }
  }

  /** Resume with the remaining time once every pause reason is gone. */
  function resumeToast(id: number, reason: ToastPauseReason): void {
    const timer = timers.get(id);
    if (!timer || !timer.pausedBy.has(reason)) return;
    timer.pausedBy.delete(reason);
    if (timer.pausedBy.size === 0 && timer.handle === null) {
      arm(id, timer, timer.remaining);
    }
  }

  /** Where focus should go if this toast is dismissed and no toast remains. */
  function returnFocusFor(id: number): HTMLElement | null {
    return returnFocus.get(id) ?? null;
  }

  const info = (text: string) => push(text, "info");
  const success = (text: string) => push(text, "success");
  const error = (text: string) => push(text, "error");

  return {
    toasts,
    push,
    dismiss,
    pauseToast,
    resumeToast,
    returnFocusFor,
    info,
    success,
    error,
  };
});
