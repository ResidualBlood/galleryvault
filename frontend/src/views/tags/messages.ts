import { i18n } from "@/i18n";
import enTags from "@/locales/en/tags.json";
import zhTags from "@/locales/zh/tags.json";

let registered = false;

export function ensureTagsMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { tagsPage: zhTags });
  i18n.global.mergeLocaleMessage("en", { tagsPage: enTags });
}
