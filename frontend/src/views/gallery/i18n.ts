import { i18n } from "@/i18n";
import enGallery from "@/locales/en/gallery.json";
import zhGallery from "@/locales/zh/gallery.json";

/**
 * The gallery detail feature owns its messages. Register them when the view
 * (or a test) loads instead of growing the global i18n entry point from every
 * feature batch.
 */
i18n.global.mergeLocaleMessage("zh", { gallery: zhGallery });
i18n.global.mergeLocaleMessage("en", { gallery: enGallery });

export {};
