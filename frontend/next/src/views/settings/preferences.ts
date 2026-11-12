import { useSettingsStore } from "@/stores/settings";
import {
  clampSlideshowInterval,
  readReaderFit,
  readReaderMode,
  readSlideshowInterval,
  writeReaderFit,
  writeReaderMode,
  writeSlideshowInterval,
} from "@/reader/storage";
import { readOnlineImageMode, writeOnlineImageMode } from "@/reader/sources/mode";
import { loadOnlineDefaults, saveOnlineDefaults } from "@/stores/online";
import { readDefaultFavcat, rememberDefaultFavcat } from "@/stores/favorites";
import type { SettingField } from "./schema";

/**
 * localStorage-backed rows (PLAN §4.2 groups 1–4).
 *
 * Reads go through the modules that already own each key so the settings page
 * never forks a second source of truth (reader, online list, quick actions and
 * the theme store keep reading the same values).
 */
export function readPreference(key: string): unknown {
  const settings = useSettingsStore();
  switch (key) {
    case "gv_theme":
      return settings.theme;
    case "gv_lang":
      return settings.lang;
    case "gv_page_size":
      return settings.pageSize;
    case "gv_reader_mode":
      return readReaderMode();
    case "gv_reader_fit":
      return readReaderFit();
    case "gv_slideshow_interval":
      return readSlideshowInterval();
    case "gv_online_image_mode":
      return readOnlineImageMode();
    case "gv_default_favcat": {
      const value = readDefaultFavcat();
      return value === null ? "0" : String(value);
    }
    case "gv_online_defaults": {
      const filters = loadOnlineDefaults();
      return {
        list: filters.list,
        tl: filters.tl,
        min_rating: filters.min_rating,
      };
    }
    default:
      return undefined;
  }
}

export function writePreference(key: string, value: unknown): void {
  const settings = useSettingsStore();
  switch (key) {
    case "gv_theme":
      settings.setTheme(value === "light" || value === "system" ? value : "dark");
      break;
    case "gv_lang":
      settings.setLang(value === "en" ? "en" : "zh");
      break;
    case "gv_page_size":
      settings.setPageSize(Number(value) || 50);
      break;
    case "gv_reader_mode":
      writeReaderMode(value === "rtl" || value === "double" || value === "double-rtl" || value === "webtoon" ? value : "ltr");
      break;
    case "gv_reader_fit":
      writeReaderFit(value === "width" || value === "original" ? value : "height");
      break;
    case "gv_slideshow_interval":
      writeSlideshowInterval(Number(value) || clampSlideshowInterval(null));
      break;
    case "gv_online_image_mode":
      writeOnlineImageMode(value === "proxy" ? "proxy" : "direct");
      break;
    case "gv_default_favcat":
      rememberDefaultFavcat(Number(value));
      break;
    case "gv_online_defaults": {
      const next = (value ?? {}) as {
        list?: unknown;
        tl?: unknown;
        min_rating?: unknown;
      };
      const current = loadOnlineDefaults();
      saveOnlineDefaults({
        ...current,
        list: typeof next.list === "string" ? (next.list as typeof current.list) : current.list,
        tl: Number(next.tl) || current.tl,
        min_rating:
          next.min_rating === null || next.min_rating === undefined
            ? null
            : Number(next.min_rating),
      });
      break;
    }
    default:
      break;
  }
}

/** Draft shape for one field: control-friendly (arrays become newline text). */
export function controlValue(field: SettingField, value: unknown): unknown {
  if (field.control === "textarea" && field.list) {
    return Array.isArray(value)
      ? value.map((entry) => String(entry)).join("\n")
      : String(value ?? "");
  }
  if (field.control === "switch") return Boolean(value);
  if (field.control === "number") {
    if (value === null || value === undefined || value === "") return "";
    return String(value);
  }
  if (field.control === "text" && Array.isArray(value)) {
    return value.map((entry) => String(entry)).join(", ");
  }
  if (field.control === "online-defaults") {
    const filters = (value ?? {}) as {
      list?: unknown;
      tl?: unknown;
      min_rating?: unknown;
    };
    return {
      list: typeof filters.list === "string" ? filters.list : "search",
      tl: String(filters.tl ?? 15),
      min_rating:
        filters.min_rating === null || filters.min_rating === undefined
          ? ""
          : String(filters.min_rating),
    };
  }
  return value ?? "";
}

export function listFromText(value: unknown): string[] {
  const parts = Array.isArray(value)
    ? value.map((entry) => String(entry))
    : String(value ?? "").split(/[\n,]/);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of parts) {
    const item = part.trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    out.push(item);
  }
  return out;
}
