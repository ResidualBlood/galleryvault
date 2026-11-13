import { i18n } from "@/i18n";
import enTagsUi from "@/locales/en/tags-ui.json";
import zhTagsUi from "@/locales/zh/tags-ui.json";
import enGallery from "@/locales/en/gallery.json";
import zhGallery from "@/locales/zh/gallery.json";

/**
 * Tag components own their copy (`tagsUi.*`) and the namespace titles the
 * chips and group headings need (`gallery.namespaces.*`). Merging at import
 * time keeps the feature self-contained; the detail views keep merging the
 * full gallery bundle through `views/gallery/i18n.ts`.
 */
i18n.global.mergeLocaleMessage("zh", {
  tagsUi: zhTagsUi,
  gallery: zhGallery,
});
i18n.global.mergeLocaleMessage("en", {
  tagsUi: enTagsUi,
  gallery: enGallery,
});
