import { i18n } from "@/i18n";
import zhDownloads from "@/locales/zh/downloads.json";
import enDownloads from "@/locales/en/downloads.json";

let registered = false;

export function ensureDownloadsMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { downloads: zhDownloads });
  i18n.global.mergeLocaleMessage("en", { downloads: enDownloads });
}
