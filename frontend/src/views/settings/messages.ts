import { i18n } from "@/i18n";
import zhSettings from "@/locales/zh/settings.json";
import enSettings from "@/locales/en/settings.json";

let registered = false;

/**
 * The settings view owns its messages (same pattern as views/library).
 * The scaffold i18n entry point is outside this batch's scope.
 */
export function ensureSettingsMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { settings: zhSettings });
  i18n.global.mergeLocaleMessage("en", { settings: enSettings });
}
