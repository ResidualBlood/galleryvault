/**
 * Small bounded image preloader.
 *
 * At most `limit` HTTP requests are in flight (2 by default, matching the
 * reader budget). Pages known to be broken are skipped; an error while
 * preloading marks the page failed so the reader can render its placeholder
 * without issuing the same request again.
 */

export interface PreloadPoolOptions {
  limit?: number;
  onError?: (url: string) => void;
}

export class PreloadPool {
  private readonly limit: number;
  private readonly onError?: (url: string) => void;
  private readonly queue: string[] = [];
  private readonly known = new Set<string>();
  private active = 0;

  constructor(options: PreloadPoolOptions = {}) {
    this.limit = Math.max(1, options.limit ?? 2);
    this.onError = options.onError;
  }

  preload(urls: readonly string[]): void {
    for (const url of urls) {
      if (!url || this.known.has(url)) continue;
      this.known.add(url);
      this.queue.push(url);
    }
    this.pump();
  }

  private pump(): void {
    while (this.active < this.limit && this.queue.length > 0) {
      const url = this.queue.shift();
      if (!url) break;
      this.active += 1;
      const image = new Image();
      const settle = (failed: boolean) => {
        this.active -= 1;
        if (failed) this.onError?.(url);
        this.pump();
      };
      image.onload = () => settle(false);
      image.onerror = () => settle(true);
      image.src = url;
    }
  }

  dispose(): void {
    this.queue.length = 0;
    this.known.clear();
  }
}
