import { afterEach, describe, expect, it, vi } from "vitest";
import { startVisiblePolling, type VisibilitySource } from "../poll";
import {
  canOpenGallery,
  errorSummary,
  formatDuration,
  formatSpeed,
  parseDownloadLinks,
  taskPercent,
} from "../format";

function fakeDocument(hidden = false): VisibilitySource & { setHidden: (value: boolean) => void } {
  const listeners = new Set<() => void>();
  const source = {
    hidden,
    addEventListener(_type: "visibilitychange", listener: () => void) {
      listeners.add(listener);
    },
    removeEventListener(_type: "visibilitychange", listener: () => void) {
      listeners.delete(listener);
    },
    setHidden(value: boolean) {
      source.hidden = value;
      for (const listener of listeners) listener();
    },
  };
  return source;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("downloads visible polling", () => {
  it("pauses ticks while the page is hidden and resumes on visibilitychange", () => {
    vi.useFakeTimers();
    const source = fakeDocument();
    const tick = vi.fn();
    const poller = startVisiblePolling(tick, 1000, source);

    expect(tick).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(3000);
    expect(tick).toHaveBeenCalledTimes(4);

    source.setHidden(true);
    vi.advanceTimersByTime(5000);
    expect(tick).toHaveBeenCalledTimes(4);

    source.setHidden(false);
    expect(tick).toHaveBeenCalledTimes(5);
    vi.advanceTimersByTime(1000);
    expect(tick).toHaveBeenCalledTimes(6);

    poller.stop();
    vi.advanceTimersByTime(5000);
    expect(tick).toHaveBeenCalledTimes(6);
  });
});

describe("downloads parsing and formatting", () => {
  it("parses URLs, compact gid/token pairs and de-duplicates gids", () => {
    expect(
      parseDownloadLinks(
        "https://e-hentai.org/g/123456/abcdef/\n123456/abcdef\n987/abc123\nnonsense\n",
      ),
    ).toEqual([
      { gid: 123456, token: "abcdef" },
      { gid: 987, token: "abc123" },
    ]);
  });

  it("only opens finished rows whose gid is already in the local library", () => {
    expect(canOpenGallery({ status: "success", gallery_id: 12 })).toBe(true);
    expect(canOpenGallery({ status: "pending", gallery_id: 12 })).toBe(false);
    expect(canOpenGallery({ status: "success", gallery_id: null })).toBe(false);
    expect(canOpenGallery({ status: "success" })).toBe(false);
  });

  it("formats speed, ETA, progress and gone errors", () => {
    expect(formatSpeed(1536)).toBe("1.5 KB/s");
    expect(formatDuration(3725)).toBe("1h 2m");
    expect(taskPercent(3, 10)).toBe(30);
    expect(taskPercent(3, null)).toBeNull();
    expect(errorSummary("GalleryGoneError: deleted")).toBe("gone");
    expect(errorSummary("network down")).toBe("network down");
  });
});
