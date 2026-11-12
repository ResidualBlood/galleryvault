import { i18n } from "@/i18n";
import zhHistory from "@/locales/zh/history.json";
import enHistory from "@/locales/en/history.json";

let registered = false;

export function ensureHistoryMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { history: zhHistory });
  i18n.global.mergeLocaleMessage("en", { history: enHistory });
}
