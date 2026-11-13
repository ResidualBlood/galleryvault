import { i18n } from "@/i18n";
import zhKit from "@/locales/zh/kit.json";
import enKit from "@/locales/en/kit.json";

let registered = false;

/**
 * Layout-kit strings (page header, toolbar overflow, pager, selection bar and
 * filter affordances) register themselves so every consumer gets them without
 * touching the scaffold i18n entry point.
 */
export function ensureLayoutMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { kit: zhKit });
  i18n.global.mergeLocaleMessage("en", { kit: enKit });
}
