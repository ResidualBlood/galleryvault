import {
  READER_FITS,
  READER_MODES,
  type ReaderFit,
  type ReaderMode,
} from "./pure";

export const READER_MODE_KEY = "gv_reader_mode";
export const READER_FIT_KEY = "gv_reader_fit";
export const SLIDESHOW_INTERVAL_KEY = "gv_slideshow_interval";
export const DEFAULT_SLIDESHOW_INTERVAL = 5;

function readStorage(key: string): string | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(key, value);
  } catch {
    /* private mode / blocked storage: keep the in-memory value for this tab */
  }
}

function isReaderMode(value: string | null): value is ReaderMode {
  return value !== null && (READER_MODES as readonly string[]).includes(value);
}

export function readReaderMode(): ReaderMode {
  const stored = readStorage(READER_MODE_KEY);
  return isReaderMode(stored) ? stored : "ltr";
}

export function writeReaderMode(mode: ReaderMode): void {
  writeStorage(READER_MODE_KEY, mode);
}

export function readReaderFit(): ReaderFit {
  const stored = readStorage(READER_FIT_KEY);
  return stored !== null && (READER_FITS as readonly string[]).includes(stored)
    ? (stored as ReaderFit)
    : "height";
}

export function writeReaderFit(fit: ReaderFit): void {
  writeStorage(READER_FIT_KEY, fit);
}

export function clampSlideshowInterval(value: number | string | null): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_SLIDESHOW_INTERVAL;
  return Math.min(600, Math.max(1, parsed));
}

export function readSlideshowInterval(): number {
  return clampSlideshowInterval(readStorage(SLIDESHOW_INTERVAL_KEY));
}

export function writeSlideshowInterval(seconds: number): number {
  const clamped = clampSlideshowInterval(seconds);
  writeStorage(SLIDESHOW_INTERVAL_KEY, String(clamped));
  return clamped;
}
