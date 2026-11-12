import { i18n } from "@/i18n";
import zhFavorites from "@/locales/zh/favorites.json";
import enFavorites from "@/locales/en/favorites.json";

let registered = false;

export function ensureFavoritesMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { favorites: zhFavorites });
  i18n.global.mergeLocaleMessage("en", { favorites: enFavorites });
}
