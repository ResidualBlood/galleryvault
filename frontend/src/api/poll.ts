/**
 * Sleep that resolves early when the caller aborts an in-flight poll.
 *
 * Background task endpoints answer 202 immediately, so the UI polls a status
 * endpoint; aborting the page-owned controller must also release the timer.
 */
export function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
