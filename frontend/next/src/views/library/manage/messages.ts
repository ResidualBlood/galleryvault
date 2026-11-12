import { i18n } from "@/i18n";
import enLibraryManage from "@/locales/en/library-manage.json";
import zhLibraryManage from "@/locales/zh/library-manage.json";

let registered = false;

/** Merge the library-management namespace exactly once per session. */
export function ensureLibraryManageMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { libraryManage: zhLibraryManage });
  i18n.global.mergeLocaleMessage("en", { libraryManage: enLibraryManage });
}
