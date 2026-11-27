import type { GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
import type { OnlineCategory } from "@/stores/online";

export const ONLINE_CATEGORY_KEYS: Record<OnlineCategory, string> = {
  doujinshi: "catDoujinshi",
  manga: "catManga",
  artistcg: "catArtistcg",
  gamecg: "catGamecg",
  western: "catWestern",
  "non-h": "catNonH",
  image_set: "catImageSet",
  cosplay: "catCosplay",
  asianporn: "catAsianporn",
  misc: "catMisc",
};

export const ONLINE_CATEGORY_TOKENS: Record<OnlineCategory, string> = {
  doujinshi: "--gv-cat-doujinshi",
  manga: "--gv-cat-manga",
  artistcg: "--gv-cat-artistcg",
  gamecg: "--gv-cat-gamecg",
  western: "--gv-cat-western",
  "non-h": "--gv-cat-nonh",
  image_set: "--gv-cat-imageset",
  cosplay: "--gv-cat-cosplay",
  asianporn: "--gv-cat-asianporn",
  misc: "--gv-cat-misc",
};

/** Backend category names → chip token (unknown categories fall back to misc). */
export function categoryToken(category: string | null | undefined): string {
  const key = (category ?? "").trim().toLowerCase().replace(/[- ]/g, "_");
  const normalized = key === "non_h" ? "non-h" : key;
  return ONLINE_CATEGORY_TOKENS[normalized as OnlineCategory] ?? "--gv-cat-misc";
}

export function categoryI18nKey(category: string | null | undefined): string {
  const key = (category ?? "").trim().toLowerCase().replace(/[- ]/g, "_");
  const normalized = key === "non_h" ? "non-h" : key;
  return `legacy.${ONLINE_CATEGORY_KEYS[normalized as OnlineCategory] ?? "catMisc"}`;
}

export function categoryBadge(category: string | null | undefined, label: string): GalleryBadge {
  return {
    label,
    tone: "category",
    colorToken: categoryToken(category),
    title: label,
  };
}
