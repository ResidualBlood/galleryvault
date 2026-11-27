import { i18n } from "@/i18n";
import enSeries from "@/locales/en/series.json";
import zhSeries from "@/locales/zh/series.json";

let registered = false;

export function ensureSeriesMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { seriesPage: zhSeries });
  i18n.global.mergeLocaleMessage("en", { seriesPage: enSeries });
}
