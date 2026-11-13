<script setup lang="ts">
/**
 * History list row.
 *
 * History entries have no tags and no cover payload, so the generic
 * GalleryListRow would print an author / size / rating / favourite line full of
 * placeholders. This row keeps exactly the history fields (audit HS-05): a
 * placeholder cover with the category colour, a single-line title, a 4px
 * progress bar with `current / total`, the last-read time and the
 * continue-reading / reset actions.
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import HistoryActions from "./HistoryActions.vue";
import type { GalleryItem } from "@/api/library";
import type { HistoryEntry } from "@/api/history";

const props = defineProps<{
  item: GalleryItem;
  entry: HistoryEntry;
  readPage?: number;
}>();

const emit = defineEmits<{ reset: [] }>();

const { t, locale } = useI18n();

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

const title = computed(() => props.item.title);
const category = computed(() => props.entry.category ?? "misc");
const categoryLabel = computed(() =>
  t(`legacy.${CATEGORY_KEYS[category.value] ?? "catMisc"}`),
);
const categoryStyle = computed(() => ({
  "--gv-row-cat": `var(${CATEGORY_TOKENS[category.value] ?? "--gv-cat-misc"})`,
}));

const total = computed(() => props.entry.total_pages ?? 0);
const current = computed(() =>
  total.value > 0 ? Math.min((props.entry.current_page ?? 0) + 1, total.value) : 0,
);
const percent = computed(() =>
  total.value > 0 ? Math.min(100, Math.round((current.value / total.value) * 100)) : 0,
);
const progressLabel = computed(() => `${current.value}/${total.value || "?"}`);

const readAt = computed(() => {
  const value = props.entry.last_read_at;
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat(locale.value === "zh" ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
});

const detailTo = computed(() => ({ name: "gallery", params: { id: props.item.id } }));
</script>

<template>
  <div class="history-row-card">
    <RouterLink
      class="history-row-card__link"
      :to="detailTo"
      :aria-label="title"
    />

    <div class="history-row-card__cover" aria-hidden="true">
      <img
        v-if="item.cover_url"
        class="history-row-card__image"
        :src="item.cover_url"
        alt=""
        loading="lazy"
        decoding="async"
      />
      <template v-else>
        <span class="history-row-card__dot" :style="categoryStyle" />
        <span class="history-row-card__no-cover">{{ t("legacy.noCover") }}</span>
      </template>
    </div>

    <div class="history-row-card__body">
      <h3 class="history-row-card__title" :title="title">{{ title }}</h3>
      <div class="history-row-card__meta">
        <span class="history-row-card__category" :style="categoryStyle">
          <span class="history-row-card__dot" aria-hidden="true" />
          <span class="history-row-card__category-label">{{ categoryLabel }}</span>
        </span>
        <span
          class="history-row-card__progress"
          role="progressbar"
          :aria-valuenow="current"
          :aria-valuemin="0"
          :aria-valuemax="total || undefined"
          :aria-label="t('history.page.progressLine', { current, total: total || '?' })"
        >
          <span class="history-row-card__progress-fill" :style="{ width: `${percent}%` }" />
        </span>
        <span class="history-row-card__pages">{{ progressLabel }}</span>
        <span v-if="readAt" class="history-row-card__date">{{ readAt }}</span>
      </div>
    </div>

    <HistoryActions
      :item="item"
      :read-page="readPage"
      class="history-row-card__actions"
      @reset="emit('reset')"
    />
  </div>
</template>

<style scoped>
.history-row-card {
  position: relative;
  display: flex;
  gap: var(--gv-space-3);
  align-items: center;
  height: var(--gv-size-list-row);
  min-width: 0;
  padding: var(--gv-space-3);
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.history-row-card__link {
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: var(--gv-radius-md);
}

.history-row-card__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.history-row-card__cover {
  position: relative;
  display: flex;
  flex: none;
  flex-direction: column;
  gap: var(--gv-space-1);
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 128px;
  overflow: hidden;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.history-row-card__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.history-row-card__no-cover {
  text-align: center;
}

.history-row-card__dot {
  display: block;
  flex: none;
  width: var(--gv-space-1);
  height: var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-row-cat, var(--gv-color-primary));
}

.history-row-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.history-row-card__title {
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-row-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.history-row-card__category {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  height: 20px;
  max-width: 50%;
  padding: 0 var(--gv-space-1);
  overflow: hidden;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  white-space: nowrap;
}

.history-row-card__category .history-row-card__dot {
  background: var(--gv-row-cat, var(--gv-color-primary));
}

.history-row-card__category-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-row-card__progress {
  flex: 0 1 96px;
  height: var(--gv-space-1);
  overflow: hidden;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-outline-variant);
}

.history-row-card__progress-fill {
  display: block;
  height: 100%;
  background: var(--gv-color-primary);
}

.history-row-card__pages,
.history-row-card__date {
  flex: none;
  white-space: nowrap;
}

.history-row-card__date {
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-row-card__actions {
  position: relative;
  z-index: 3;
  flex: none;
}

@media (max-width: 599.98px) {
  .history-row-card {
    gap: var(--gv-space-2);
    padding: var(--gv-space-2);
  }

  .history-row-card__cover {
    width: 80px;
    height: 107px;
  }
}
</style>
