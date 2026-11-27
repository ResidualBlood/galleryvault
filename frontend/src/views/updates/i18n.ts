import { i18n } from "@/i18n";
import zhMaintenance from "@/locales/zh/maintenance.json";
import enMaintenance from "@/locales/en/maintenance.json";

let registered = false;

/**
 * The maintenance views (updates / duplicates / recycle / integrity) own their
 * message namespace. The scaffold i18n entry point is outside this batch's
 * scope, so merge once when the first maintenance view loads.
 */
export function ensureMaintenanceMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { maintenance: zhMaintenance });
  i18n.global.mergeLocaleMessage("en", { maintenance: enMaintenance });
}
