import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { setLocale, type Lang } from "@/i18n";

export type ThemeChoice = "dark" | "light" | "system";

const THEME_KEY = "gv_theme";
const LANG_KEY = "gv_lang";
const PAGE_SIZE_KEY = "gv_page_size";

function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocal(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage may be blocked; the in-memory value still works for this tab */
  }
}

function systemTheme(): "dark" | "light" {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/**
 * Frontend-only preferences. Keys intentionally match the legacy frontend so
 * upgrading and rolling back keep the user's choices (inv-frontend.md §3.5).
 */
export const useSettingsStore = defineStore("settings", () => {
  const storedTheme = readLocal(THEME_KEY);
  const theme = ref<ThemeChoice>(
    storedTheme === "light" || storedTheme === "system" ? storedTheme : "dark",
  );
  const storedLang = readLocal(LANG_KEY);
  const lang = ref<Lang>(storedLang === "en" ? "en" : "zh");
  const pageSize = ref(Number(readLocal(PAGE_SIZE_KEY)) || 50);

  const effectiveTheme = computed<"dark" | "light">(() =>
    theme.value === "system" ? systemTheme() : theme.value,
  );

  function applyTheme(): void {
    if (typeof document === "undefined") return;
    if (theme.value === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", theme.value);
    }
  }

  function setTheme(next: ThemeChoice): void {
    theme.value = next;
    writeLocal(THEME_KEY, next);
    applyTheme();
  }

  function cycleTheme(): ThemeChoice {
    const order: ThemeChoice[] = ["dark", "light", "system"];
    const next = order[(order.indexOf(theme.value) + 1) % order.length];
    setTheme(next);
    return next;
  }

  function setLang(next: Lang): void {
    lang.value = next;
    writeLocal(LANG_KEY, next);
    setLocale(next);
  }

  function toggleLang(): Lang {
    const next: Lang = lang.value === "zh" ? "en" : "zh";
    setLang(next);
    return next;
  }

  function setPageSize(size: number): void {
    if (!Number.isFinite(size) || size <= 0) return;
    pageSize.value = size;
    writeLocal(PAGE_SIZE_KEY, String(size));
  }

  function init(): void {
    applyTheme();
    setLocale(lang.value);
  }

  return {
    theme,
    effectiveTheme,
    lang,
    pageSize,
    init,
    applyTheme,
    setTheme,
    cycleTheme,
    setLang,
    toggleLang,
    setPageSize,
  };
});
