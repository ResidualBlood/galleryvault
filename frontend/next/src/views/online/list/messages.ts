import { i18n } from "@/i18n";
import zhOnline from "@/locales/zh/online.json";
import enOnline from "@/locales/en/online.json";

let registered = false;

/**
 * Online views own their messages (same pattern as views/library/messages.ts).
 * The scaffold i18n entry point is outside this batch's scope.
 */
export function ensureOnlineMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { online: zhOnline });
  i18n.global.mergeLocaleMessage("en", { online: enOnline });
}
