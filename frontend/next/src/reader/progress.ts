/**
 * Serialised reading-progress writes with a latest-intent queue and retries.
 *
 * Legacy behaviour kept: only one PUT is in flight per gallery and only the
 * newest intent is kept. The improvement required by inv-frontend.md §8.5 is
 * that a failed PUT is retried instead of being swallowed, so a transient 500
 * or network blip cannot silently lose the last page.
 */

export interface ProgressPayload {
  current_page: number;
  total_pages: number;
}

export type ProgressSender = (payload: ProgressPayload) => Promise<unknown>;

export interface ProgressWriterOptions {
  send: ProgressSender;
  debounceMs?: number;
  retryDelayMs?: number;
  retries?: number;
}

interface PendingJob extends ProgressPayload {
  attempts: number;
}

export class ProgressWriter {
  private readonly send: ProgressSender;
  private readonly debounceMs: number;
  private readonly retryDelayMs: number;
  private readonly maxRetries: number;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pending: PendingJob | null = null;
  private inflight = false;
  private disposed = false;

  constructor(options: ProgressWriterOptions) {
    this.send = options.send;
    this.debounceMs = options.debounceMs ?? 500;
    this.retryDelayMs = options.retryDelayMs ?? 1_000;
    this.maxRetries = options.retries ?? 3;
  }

  queue(page: number, total: number, options: { immediate?: boolean } = {}): void {
    if (this.disposed) return;
    if (!Number.isFinite(page) || !Number.isFinite(total) || total <= 0) return;
    const safePage = Math.max(0, Math.min(Math.floor(page), Math.floor(total) - 1));
    this.pending = {
      current_page: safePage,
      total_pages: Math.floor(total),
      attempts: this.pending?.attempts ?? 0,
    };
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (options.immediate) {
      this.flush();
      return;
    }
    this.timer = setTimeout(() => {
      this.timer = null;
      this.flush();
    }, this.debounceMs);
  }

  /** Force the current intent out now (pagehide / gallery change). */
  flushNow(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.flush();
  }

  private flush(): void {
    if (this.disposed || this.inflight || !this.pending) return;
    const job = this.pending;
    this.pending = null;
    this.inflight = true;
    this.send({ current_page: job.current_page, total_pages: job.total_pages })
      .then(() => {
        this.inflight = false;
        if (this.disposed) return;
        // A newer intent arrived while this write was in flight; send it now.
        if (this.pending) this.flush();
      })
      .catch(() => {
        this.inflight = false;
        if (this.disposed) return;
        const next: PendingJob = this.pending ?? { ...job, attempts: job.attempts };
        next.attempts += 1;
        this.pending = next;
        if (next.attempts > this.maxRetries) return;
        this.retryTimer = setTimeout(() => {
          this.retryTimer = null;
          this.flush();
        }, this.retryDelayMs);
      });
  }

  dispose(): void {
    this.disposed = true;
    if (this.timer !== null) clearTimeout(this.timer);
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.timer = null;
    this.retryTimer = null;
    this.pending = null;
  }
}
