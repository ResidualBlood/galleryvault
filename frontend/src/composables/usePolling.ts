import { getCurrentScope, onScopeDispose, ref } from "vue";

export interface PollingOptions {
  /** Run immediately on start (default true). */
  immediate?: boolean;
  /** Skip ticks while the document is hidden (default true). */
  pauseWhenHidden?: boolean;
}

/**
 * Visibility-aware interval polling. The rewrite deliberately keeps polling
 * (the backend exposes no SSE/WebSocket endpoints, inv-frontend.md §1.3).
 * A tick never overlaps the previous one.
 */
export function usePolling(
  task: () => Promise<unknown> | unknown,
  intervalMs: number,
  options: PollingOptions = {},
) {
  const running = ref(false);
  const busy = ref(false);
  const lastError = ref<unknown>(null);
  let timer: ReturnType<typeof setInterval> | null = null;

  const pauseWhenHidden = options.pauseWhenHidden ?? true;

  async function tick(): Promise<void> {
    if (!running.value || busy.value) return;
    if (pauseWhenHidden && typeof document !== "undefined" && document.hidden) return;
    busy.value = true;
    try {
      await task();
      lastError.value = null;
    } catch (error) {
      lastError.value = error;
    } finally {
      busy.value = false;
    }
  }

  function start(): void {
    if (running.value) return;
    running.value = true;
    if (options.immediate !== false) void tick();
    timer = setInterval(() => void tick(), Math.max(250, intervalMs));
  }

  function stop(): void {
    running.value = false;
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  if (getCurrentScope()) onScopeDispose(stop);

  return { running, busy, lastError, start, stop, tick };
}
