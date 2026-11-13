<script setup lang="ts">
/**
 * One table row (DESIGN.md C18): 56px high, cells follow the shared column
 * model, tags are inline with `3 + N`, missing values render an em dash.
 * The row itself is a link overlay; tags / selection / actions keep their own
 * pointer events so they never navigate to the detail page.
 */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import { ensureCollectionMessages } from "./collection-messages";
import { columnTemplate, type TableColumn } from "./table-columns";
import TagList from "@/components/tags/TagList.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import { useTagNavigation, type TagSource } from "@/components/tags/useTagNavigation";
import { type TagLike, type TagMenuEvent } from "@/components/tags/tag-utils";
import Icon from "@/components/icons/Icon.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import { formatBytes, formatDate, progressPercent } from "@/stores/library";
import type { GalleryItem } from "@/api/library";

ensureCollectionMessages();

const props = withDefaults(
  defineProps<{
    item: GalleryItem;
    columns: TableColumn[];
    source?: "local" | "online";
    selectable?: boolean;
    selected?: boolean;
    tagSource?: TagSource;
  }>(),
  {
    source: "local",
    selectable: false,
    selected: false,
    tagSource: undefined,
  },
);

defineEmits<{
  open: [item: GalleryItem];
  select: [id: number, selected: boolean];
}>();

const { t } = useI18n();

const CATEGORY_LABELS: Record<string, string> = {
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

const template = computed(() => columnTemplate(props.columns));

const coverSrc = computed(() => {
  const value = props.item.cover_url?.trim() ?? "";
  if (!value) return "";
  if (value.includes("\\")) return "";
  return /^(data:image\/(png|jpeg|gif|webp);base64,|https?:\/\/|\/(?!\/))/i.test(value)
    ? value
    : "";
});

const detailTo = computed(() => {
  if (props.source === "online" && props.item.gid && props.item.token) {
    return { name: "online-detail", params: { gid: props.item.gid, token: props.item.token } };
  }
  return { name: "gallery", params: { id: props.item.id } };
});

const ariaLabel = computed(() => `${props.item.title} (${props.item.page_count}P)`);

const tags = computed<TagLike[]>(() => props.item.tags ?? []);
const tagCount = computed(() => props.item.tag_count ?? tags.value.length);

const categoryLabel = computed(() =>
  t(`legacy.${CATEGORY_LABELS[props.item.category] ?? "catMisc"}`),
);
const categoryToken = computed(
  () => CATEGORY_TOKENS[props.item.category] ?? "--gv-cat-misc",
);
const categoryStyle = computed(() => ({
  "--gv-row-cat": `var(${categoryToken.value})`,
}));

const uploader = computed(() => props.item.uploader?.trim() || t("collection.list.empty"));
const sizeText = computed(() => formatBytes(props.item.file_size) || t("collection.list.empty"));
const dateText = computed(() => formatDate(props.item.posted_at) || t("collection.list.empty"));

const progress = computed(() => {
  const current = props.item.reading_progress ?? 0;
  if (current <= 0 || props.item.page_count <= 0) return null;
  return {
    current,
    total: props.item.page_count,
    percent: progressPercent(current, props.item.page_count),
  };
});

const progressText = computed(() => {
  if (progress.value) {
    return `${progress.value.current}/${progress.value.total}`;
  }
  return t("collection.list.empty");
});

const rating = computed(() =>
  typeof props.item.rating === "number" && props.item.rating > 0 ? props.item.rating : null,
);
const ratingText = computed(() => (rating.value ? rating.value.toFixed(1) : t("collection.list.empty")));
const ratingLabel = computed(() =>
  rating.value
    ? t("collection.rating.label", { value: rating.value.toFixed(1) })
    : t("collection.rating.none"),
);

const favorited = computed(() => Boolean(props.item.favorite));
const inLibrary = computed(() => Boolean(props.item.in_library));
const downloadStatus = computed(() => props.item.download_status ?? "");

const tagSource = computed<TagSource>(
  () => props.tagSource ?? (props.source === "online" ? "online" : "local"),
);
const tagNavigation = useTagNavigation(tagSource.value);
const menu = ref<TagMenuEvent | null>(null);

function onTagSelect(tag: TagLike): void {
  void tagNavigation.navigate(tag);
}

function onTagExclude(tag: TagLike): void {
  void tagNavigation.navigate(tag, { exclude: true });
}
</script>

<template>
  <div
    class="gallery-table-row"
    :class="{ 'gallery-table-row--selected': selected }"
    :style="{ gridTemplateColumns: template }"
    data-testid="gallery-table-row"
    :data-id="item.id"
    role="row"
  >
    <RouterLink
      class="gallery-table-row__link"
      :to="detailTo"
      :aria-label="ariaLabel"
      @click="$emit('open', item)"
    />

    <template v-for="column in columns" :key="column.key">
      <div
        v-if="column.key === 'selection'"
        class="gallery-table-row__cell gallery-table-row__cell--center"
        role="gridcell"
      >
        <Checkbox
          v-if="selectable"
          :model-value="selected"
          :aria-label="`${t('collection.table.select')} ${item.title}`"
          @update:model-value="$emit('select', item.id, $event)"
        />
      </div>

      <div
        v-else-if="column.key === 'cover'"
        class="gallery-table-row__cell gallery-table-row__cell--center"
        role="gridcell"
      >
        <span class="gallery-table-row__cover">
          <img
            v-if="coverSrc"
            class="gallery-table-row__image"
            :src="coverSrc"
            :alt="item.title"
            loading="lazy"
            decoding="async"
          />
          <span v-else class="gallery-table-row__cover-empty" aria-hidden="true" />
        </span>
      </div>

      <div
        v-else-if="column.key === 'title'"
        class="gallery-table-row__cell gallery-table-row__cell--title"
        role="gridcell"
      >
        <span class="gallery-table-row__title" :title="item.title">{{ item.title }}</span>
      </div>

      <div
        v-else-if="column.key === 'category'"
        class="gallery-table-row__cell"
        role="gridcell"
      >
        <span class="gallery-table-row__category" :style="categoryStyle">
          <span class="gallery-table-row__dot" aria-hidden="true" />
          <span class="gallery-table-row__category-label">{{ categoryLabel }}</span>
        </span>
      </div>

      <div
        v-else-if="column.key === 'tags'"
        class="gallery-table-row__cell gallery-table-row__cell--tags"
        role="gridcell"
      >
        <TagList
          v-if="tagCount > 0"
          :tags="tags"
          :tag-count="tagCount"
          :max="3"
          :size="24"
          :source="source"
          @select="onTagSelect"
          @exclude="onTagExclude"
          @menu="menu = $event"
        />
        <span v-else class="gallery-table-row__muted">{{ t("collection.list.empty") }}</span>
      </div>

      <div
        v-else-if="column.key === 'uploader'"
        class="gallery-table-row__cell gallery-table-row__cell--ellipsis"
        role="gridcell"
        :title="uploader"
      >
        {{ uploader }}
      </div>

      <div
        v-else-if="column.key === 'pages'"
        class="gallery-table-row__cell gallery-table-row__cell--end"
        role="gridcell"
      >
        {{ item.page_count > 0 ? t("collection.list.pages", { count: item.page_count }) : t("collection.list.empty") }}
      </div>

      <div
        v-else-if="column.key === 'size'"
        class="gallery-table-row__cell gallery-table-row__cell--end"
        role="gridcell"
      >
        {{ sizeText }}
      </div>

      <div
        v-else-if="column.key === 'rating'"
        class="gallery-table-row__cell gallery-table-row__cell--rating"
        role="gridcell"
        :title="ratingLabel"
        :aria-label="ratingLabel"
      >
        <Icon :name="rating ? 'star' : 'star-empty'" size="sm" aria-hidden="true" />
        <span>{{ ratingText }}</span>
      </div>

      <div
        v-else-if="column.key === 'posted'"
        class="gallery-table-row__cell gallery-table-row__cell--end"
        role="gridcell"
      >
        {{ dateText }}
      </div>

      <div
        v-else-if="column.key === 'progress'"
        class="gallery-table-row__cell gallery-table-row__cell--end"
        role="gridcell"
      >
        {{ progressText }}
      </div>

      <div
        v-else-if="column.key === 'status'"
        class="gallery-table-row__cell gallery-table-row__cell--center gallery-table-row__states"
        role="gridcell"
      >
        <span
          class="gallery-table-row__state"
          :class="{ 'gallery-table-row__state--on': favorited }"
          :title="favorited ? t('collection.status.favorited') : t('collection.status.notFavorited')"
          :aria-label="favorited ? t('collection.status.favorited') : t('collection.status.notFavorited')"
          role="img"
        >
          <Icon :name="favorited ? 'favorite' : 'favorite-outline'" size="sm" aria-hidden="true" />
        </span>
        <span
          v-if="inLibrary"
          class="gallery-table-row__state gallery-table-row__state--on"
          :title="t('collection.status.inLibrary')"
          :aria-label="t('collection.status.inLibrary')"
          role="img"
        >
          <Icon name="library" size="sm" aria-hidden="true" />
        </span>
        <span
          v-if="downloadStatus && downloadStatus !== 'none'"
          class="gallery-table-row__state gallery-table-row__state--on"
          :title="t('collection.status.download')"
          :aria-label="`${t('collection.status.download')}: ${downloadStatus}`"
          role="img"
        >
          <Icon name="downloads" size="sm" aria-hidden="true" />
        </span>
      </div>

      <div
        v-else-if="column.key === 'actions'"
        class="gallery-table-row__cell gallery-table-row__cell--end gallery-table-row__actions"
        role="gridcell"
      >
        <slot name="actions" :item="item" />
      </div>

      <div v-else class="gallery-table-row__cell" role="gridcell">{{ t("collection.list.empty") }}</div>
    </template>

    <TagMenu
      v-if="menu"
      :tag="menu.tag"
      :x="menu.x"
      :y="menu.y"
      :source="tagSource"
      @close="menu = null"
      @copied="menu = null"
    />
  </div>
</template>

<style scoped>
.gallery-table-row {
  position: relative;
  display: grid;
  align-items: center;
  height: var(--gv-size-table-row);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface);
  transition: background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.gallery-table-row:hover {
  background: var(--gv-color-surface-container);
}

.gallery-table-row--selected {
  background: var(--gv-color-secondary-container);
}

.gallery-table-row__link {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.gallery-table-row__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.gallery-table-row__cell {
  display: flex;
  align-items: center;
  min-width: 0;
  padding: 0 var(--gv-space-3);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.gallery-table-row__cell--center {
  justify-content: center;
}

.gallery-table-row__cell--end {
  justify-content: flex-end;
  font-variant-numeric: tabular-nums;
}

.gallery-table-row__cell--title {
  font: var(--gv-type-title-small);
}

.gallery-table-row__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-table-row__cell--ellipsis {
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  text-overflow: ellipsis;
}

.gallery-table-row__cell--tags {
  position: relative;
  z-index: 3;
  pointer-events: auto;
}

.gallery-table-row__cover {
  display: block;
  width: 40px;
  height: 53px;
  overflow: hidden;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-highest);
}

.gallery-table-row__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.gallery-table-row__cover-empty {
  display: block;
  width: 100%;
  height: 100%;
}

.gallery-table-row__category {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  min-width: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
}

.gallery-table-row__dot {
  display: block;
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: var(--gv-radius-full);
  background: var(--gv-row-cat, var(--gv-cat-misc));
}

.gallery-table-row__category-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.gallery-table-row__cell--rating {
  gap: var(--gv-space-1);
  color: var(--gv-color-warning);
}

.gallery-table-row__states {
  gap: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
}

.gallery-table-row__state {
  display: inline-flex;
  align-items: center;
}

.gallery-table-row__state--on {
  color: var(--gv-color-primary-text);
}

.gallery-table-row__muted {
  color: var(--gv-color-on-surface-variant);
}

.gallery-table-row__actions {
  position: relative;
  z-index: 3;
  pointer-events: auto;
}
</style>
