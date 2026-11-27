<script setup lang="ts">
/**
 * Series member card.
 *
 * Members render through the shared GalleryCard so the grid / list views match
 * the rest of the product (audit SR-04 / SR-05): title step, two-line clamp,
 * 2px selection ring, 44px translucent selection corner and the hover tag
 * overlay all come from GalleryCard. Only the series-specific fields are
 * mapped here: source badge (local / cloud) and the category label.
 */
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import type { GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
import type { GalleryItem } from "@/api/library";
import type { SeriesMember } from "@/api/series";

const props = defineProps<{
  member: SeriesMember;
  selected: boolean;
  mode: "grid" | "list";
}>();

const emit = defineEmits<{ toggle: [member: SeriesMember, checked: boolean] }>();

const { t } = useI18n();

const CATEGORY_KEYS: Record<string, string> = {
  doujinshi: "catDoujinshi",
  manga: "catManga",
  artistcg: "catArtistcg",
  gamecg: "catGamecg",
  western: "catWestern",
  "non-h": "catNonH",
  nonh: "catNonH",
  image_set: "catImageSet",
  imageset: "catImageSet",
  cosplay: "catCosplay",
  asianporn: "catAsianporn",
  misc: "catMisc",
  other: "catMisc",
  private: "catMisc",
  deleted: "catDeleted",
};

const CATEGORY_TOKENS: Record<string, string> = {
  doujinshi: "--gv-cat-doujinshi",
  manga: "--gv-cat-manga",
  artistcg: "--gv-cat-artistcg",
  gamecg: "--gv-cat-gamecg",
  western: "--gv-cat-western",
  "non-h": "--gv-cat-nonh",
  nonh: "--gv-cat-nonh",
  image_set: "--gv-cat-imageset",
  imageset: "--gv-cat-imageset",
  cosplay: "--gv-cat-cosplay",
  asianporn: "--gv-cat-asianporn",
  misc: "--gv-cat-misc",
  other: "--gv-cat-other",
  private: "--gv-cat-private",
  deleted: "--gv-cat-other",
};

const title = computed(() => props.member.title || `gid ${props.member.gid ?? ""}`);
const isLocal = computed(() => Boolean(props.member.is_local));
const category = computed(() => props.member.category ?? "misc");
const categoryLabel = computed(() =>
  t(`legacy.${CATEGORY_KEYS[category.value] ?? "catMisc"}`),
);

const badges = computed<GalleryBadge[]>(() => [
  {
    label: categoryLabel.value,
    tone: "category",
    colorToken: CATEGORY_TOKENS[category.value] ?? "--gv-cat-misc",
    title: categoryLabel.value,
  },
  {
    label: isLocal.value ? t("seriesPage.localBadge") : t("seriesPage.cloudBadge"),
    tone: isLocal.value ? "success" : "neutral",
  },
]);

const item = computed<GalleryItem>(() => ({
  id: Number(props.member.gallery_id ?? props.member.gid ?? 0),
  gid: props.member.gid,
  token: props.member.token,
  title: title.value,
  category: category.value,
  page_count: props.member.page_count ?? 0,
  cover_url: props.member.cover_url ?? null,
  tags: props.member.tags ?? [],
  tag_count: (props.member.tags ?? []).length,
  uploader: null,
  posted_at: null,
  file_size: null,
  reading_progress: 0,
}));

const source = computed<"local" | "online">(() => (isLocal.value ? "local" : "online"));

function onSelect(_id: number, checked: boolean): void {
  emit("toggle", props.member, checked);
}
</script>

<template>
  <div
    class="series-member"
    data-testid="series-member"
    :data-local="isLocal ? '1' : '0'"
  >
    <GalleryCard
      :item="item"
      :variant="mode"
      :source="source"
      :badges="badges"
      :show-meta="false"
      selectable
      :selected="selected"
      tag-source="local"
      @select="onSelect"
    />
  </div>
</template>

<style scoped>
.series-member {
  min-width: 0;
}
</style>
