/** Pure helpers for the local gallery detail view (unit-testable). */

const CATEGORY_ALIASES: Record<string, string> = {
  "non-h": "nonh",
  nonh: "nonh",
  "image-set": "imageset",
  image_set: "imageset",
  imageset: "imageset",
  "artist-cg": "artistcg",
  artist_cg: "artistcg",
  artistcg: "artistcg",
  "game-cg": "gamecg",
  game_cg: "gamecg",
  gamecg: "gamecg",
  "asian-porn": "asianporn",
  asian_porn: "asianporn",
  asianporn: "asianporn",
  doujinshi: "doujinshi",
  manga: "manga",
  western: "western",
  cosplay: "cosplay",
  misc: "misc",
  private: "private",
  other: "other",
};

export const KNOWN_CATEGORY_KEYS = new Set(Object.values(CATEGORY_ALIASES));

/** `#/gallery/{id}` accepts a positive integer only. */
export function parseGalleryId(raw: unknown): number | null {
  if (typeof raw !== "string" && typeof raw !== "number") return null;
  const value = String(raw).trim();
  if (!/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export function categoryKey(category?: string | null): string {
  const raw = String(category ?? "")
    .trim()
    .toLowerCase();
  if (!raw) return "misc";
  const mapped = CATEGORY_ALIASES[raw] ?? raw.replace(/\s+/g, "");
  return KNOWN_CATEGORY_KEYS.has(mapped) ? mapped : "misc";
}

export function formatBytes(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return "";
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : size >= 10 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

export function formatDate(iso?: string | null, locale = "zh-CN"): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date);
  } catch {
    return date.toISOString().slice(0, 10);
  }
}

export function formatRating(rating?: number | null): string {
  if (rating === null || rating === undefined) return "";
  const value = Number(rating);
  if (!Number.isFinite(value)) return "";
  return value.toFixed(2);
}
