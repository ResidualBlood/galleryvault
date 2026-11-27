import { i18n } from "@/i18n";
import zhHistory from "@/locales/zh/history.json";
import enHistory from "@/locales/en/history.json";

let registered = false;

export function ensureHistoryMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", {
    history: zhHistory,
    // History's table reuses the collection table header; "posted" renders the
    // last-read timestamp, so only the label differs from the library table.
    collection: { table: { readAt: zhHistory.table.readAt } },
  });
  i18n.global.mergeLocaleMessage("en", {
    history: enHistory,
    collection: { table: { readAt: enHistory.table.readAt } },
  });
}
