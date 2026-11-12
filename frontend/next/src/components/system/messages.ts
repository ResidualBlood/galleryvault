import { i18n } from "@/i18n";
import zhSystem from "@/locales/zh/system.json";
import enSystem from "@/locales/en/system.json";

let registered = false;

/**
 * Logs, welcome, archive and the global/system widgets share one `system`
 * namespace so their locale files stay inside this batch's scope.
 */
export function ensureSystemMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { system: zhSystem });
  i18n.global.mergeLocaleMessage("en", { system: enSystem });
}

// Components and views only need the side-effect import; the first one to load
// registers the namespace for the whole app.
ensureSystemMessages();
