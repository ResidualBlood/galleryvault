import { createI18n } from "vue-i18n";
import zhApp from "@/locales/zh/app.json";
import zhLogin from "@/locales/zh/login.json";
import zhCommon from "@/locales/zh/common.json";
import zhLegacy from "@/locales/zh/legacy.json";
import enApp from "@/locales/en/app.json";
import enLogin from "@/locales/en/login.json";
import enCommon from "@/locales/en/common.json";
import enLegacy from "@/locales/en/legacy.json";

export type Lang = "zh" | "en";
export const LANGS: readonly Lang[] = ["zh", "en"];

/**
 * Messages are split per feature. `legacy.json` is the frozen snapshot of the
 * pre-cutover translations; the migration is complete and the legacy sources
 * have been deleted, so it is read as static data. It keeps the old
 * translations available under the `legacy.` namespace for pages that are
 * migrated one by one.
 */
export const i18n = createI18n({
  legacy: false,
  locale: "zh",
  fallbackLocale: "en",
  messages: {
    zh: { app: zhApp, login: zhLogin, common: zhCommon, legacy: zhLegacy },
    en: { app: enApp, login: enLogin, common: enCommon, legacy: enLegacy },
  },
});

export function setLocale(lang: Lang): void {
  i18n.global.locale.value = lang;
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }
}
