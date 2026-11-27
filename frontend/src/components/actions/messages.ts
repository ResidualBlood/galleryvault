import { i18n } from "@/i18n";
import zhActions from "@/locales/zh/actions.json";
import enActions from "@/locales/en/actions.json";

let registered = false;

/**
 * The action components own their messages; the scaffold i18n entry point is
 * outside this batch's scope (same pattern as views/online/list/messages.ts).
 */
export function ensureActionMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { actions: zhActions });
  i18n.global.mergeLocaleMessage("en", { actions: enActions });
}
