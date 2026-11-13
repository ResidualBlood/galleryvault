import { i18n } from "@/i18n";
import zhCollection from "@/locales/zh/collection.json";
import enCollection from "@/locales/en/collection.json";

let registered = false;

/**
 * Collection copy (view toggle, table headers, row placeholders and status
 * labels). Merged once at import time, mirroring the per-feature JSON layout
 * used by the library / tag bundles, so the gallery components never depend on
 * the scaffold's initial i18n entry point.
 */
export function ensureCollectionMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { collection: zhCollection });
  i18n.global.mergeLocaleMessage("en", { collection: enCollection });
}
