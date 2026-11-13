/** Pure helpers for the downloads view (kept separate so they are testable). */

export interface ParsedDownloadLink {
  gid: number;
  token: string;
}

/**
 * Accepts one gallery per line:
 *   - https://e-hentai.org/g/123456/abcdef/ (also exhentai)
 *   - 123456/abcdef
 */
export function parseDownloadLinks(text: string): ParsedDownloadLink[] {
  const seen = new Set<number>();
  const items: ParsedDownloadLink[] = [];
  for (const rawLine of String(text ?? "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    let gid = 0;
    let token = "";
    const href = line.match(/\/g\/(\d+)\/([A-Za-z0-9]+)/);
    if (href) {
      gid = Number.parseInt(href[1], 10);
      token = href[2];
    } else {
      const compact = line.match(/^(\d+)[\s/]+([A-Za-z0-9]+)$/);
      if (compact) {
        gid = Number.parseInt(compact[1], 10);
        token = compact[2];
      }
    }
    if (!Number.isFinite(gid) || gid <= 0 || !token || seen.has(gid)) continue;
    seen.add(gid);
    items.push({ gid, token });
  }
  return items;
}

export function formatSpeed(bytesPerSecond?: number | null): string {
  if (typeof bytesPerSecond !== "number" || !Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) {
    return "";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytesPerSecond;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = value >= 100 || unit === 0 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unit]}/s`;
}

export function formatDuration(seconds?: number | null): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return "";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

/** DL-04: only a finished download that exists in the local library can open. */
export function canOpenGallery(task: {
  status: string;
  gallery_id?: number | null;
}): boolean {
  return (
    task.status === "success" &&
    typeof task.gallery_id === "number" &&
    task.gallery_id > 0
  );
}

export function taskPercent(currentPage?: number | null, totalPages?: number | null): number | null {
  if (!totalPages || totalPages <= 0) return null;
  const current = Math.max(0, currentPage ?? 0);
  return Math.max(0, Math.min(100, Math.round((current / totalPages) * 100)));
}

export function errorSummary(message?: string | null): string {
  if (!message) return "";
  const lower = message.toLowerCase();
  if (
    lower.includes("gallerygoneerror") ||
    lower.includes("deleted or not found") ||
    lower.includes("does not exist on exhentai")
  ) {
    return "gone";
  }
  return message;
}
