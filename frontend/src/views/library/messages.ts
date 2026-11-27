import { i18n } from "@/i18n";
import zhLibrary from "@/locales/zh/library.json";
import enLibrary from "@/locales/en/library.json";

let registered = false;

/**
 * The scaffold's i18n module only imports the initial feature files (it is
 * outside this batch's scope), so the browse/library views merge their own
 * namespace exactly once. Keeping this here mirrors the per-feature JSON
 * layout documented in frontend/README.md.
 */
export function ensureLibraryMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { library: zhLibrary });
  i18n.global.mergeLocaleMessage("en", { library: enLibrary });
}
