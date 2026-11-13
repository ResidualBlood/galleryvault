<script setup lang="ts">
/**
 * List row for the collection view (DESIGN.md C18, audit BR-07/BR-08).
 *
 * Left cover 96x128 (80x107 below 600px), two title lines, one secondary line
 * (uploader / artist · date · language), inline tags with `+N` (4, or 3 on
 * narrow screens), and a bottom line with category, pages or read progress,
 * rating, size and state icons. Missing values render an em dash so the row
 * never collapses into a hole; the action slot sits at the row end and never
 * overlaps the title (audit LB-08).
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import BadgeStrip, { type GalleryBadge } from "./BadgeStrip.vue";
import { ensureCollectionMessages } from "./collection-messages";
import TagList from "@/components/tags/TagList.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import { useTagNavigation, type TagSource } from "@/components/tags/useTagNavigation";
import {
  tagLabel,
  tagNamespace,
  type TagLike,
  type TagMenuEvent,
} from "@/components/tags/tag-utils";
import Icon from "@/components/icons/Icon.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import { formatBytes, formatDate, progressPercent } from "@/stores/library";
import type { GalleryItem } from "@/api/library";

ensureCollectionMessages();

const props = withDefaults(
  defineProps<{
    item: GalleryItem;
    source?: "local" | "online";
    badges?: GalleryBadge[];
    showMeta?: boolean;
    favorited?: boolean;
    selectable?: boolean;
    selected?: boolean;
    tagSource?: TagSource;
  }>(),
  {
    source: "local",
    badges: undefined,
    showMeta: true,
    favorited: undefined,
    selectable: false,
    selected: false,
    tagSource: undefined,
  },
);

defineEmits<{
  open: [item: GalleryItem];
  select: [id: number, selected: boolean];
}>();

const { t, locale } = useI18n();

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

const categoryBadge = computed<GalleryBadge>(() => {
  const label = t(`legacy.${CATEGORY_LABELS[props.item.category] ?? "catMisc"}`);
  return {
    label,
    tone: "category",
    colorToken: CATEGORY_TOKENS[props.item.category] ?? "--gv-cat-misc",
    title: label,
  };
});

const rowBadges = computed<GalleryBadge[]>(() =>
  props.badges && props.badges.length ? props.badges : [categoryBadge.value],
);

const coverSrc = computed(() => {
  const value = props.item.cover_url?.trim() ?? "";
  if (!value) return "";
  if (value.includes("\\")) return "";
  return /^(data:image\/(png|jpeg|gif|webp);base64,|https?:\/\/|\/(?!\/))/i.test(value)
    ? value
    : "";
});

const tags = computed<TagLike[]>(() => props.item.tags ?? []);
const tagCount = computed(() => props.item.tag_count ?? tags.value.length);

const artist = computed(() => findTag("artist"));
const language = computed(() => findTag("language"));

function findTag(namespace: string): TagLike | null {
  return tags.value.find((tag) => tagNamespace(tag) === namespace) ?? null;
}

const uploader = computed(() => props.item.uploader?.trim() ?? "");
const authorLine = computed(() => {
  const artistLabel = artist.value ? tagLabel(artist.value, locale.value) : "";
  if (uploader.value && artistLabel) return `${uploader.value} / ${artistLabel}`;
  return uploader.value || artistLabel || t("collection.list.empty");
});

const dateText = computed(() => formatDate(props.item.posted_at) || t("collection.list.empty"));
const languageText = computed(() =>
  language.value ? tagLabel(language.value, locale.value) : t("collection.list.empty"),
);
const subLine = computed(() =>
  [authorLine.value, dateText.value, languageText.value].join(" · "),
);

const progress = computed(() => {
  const current = props.item.reading_progress ?? 0;
  if (current <= 0 || props.item.page_count <= 0) return null;
  return {
    current,
    total: props.item.page_count,
    percent: progressPercent(current, props.item.page_count),
  };
});

const pagesText = computed(() => {
  if (progress.value) {
    return t("collection.list.progress", {
      current: progress.value.current,
      total: progress.value.total,
    });
  }
  if (props.item.page_count > 0) {
    return t("collection.list.pages", { count: props.item.page_count });
  }
  return t("collection.list.empty");
});

const sizeText = computed(() => formatBytes(props.item.file_size) || t("collection.list.empty"));

const ratingText = computed(() =>
  typeof props.item.rating === "number" && props.item.rating > 0
    ? props.item.rating.toFixed(1)
    : t("collection.list.empty"),
);

const ratingLabel = computed(() =>
  typeof props.item.rating === "number" && props.item.rating > 0
    ? t("collection.rating.label", { value: props.item.rating.toFixed(1) })
    : t("collection.rating.none"),
);

const favorited = computed(() => props.favorited ?? Boolean(props.item.favorite));
const inLibrary = computed(() => Boolean(props.item.in_library));
const downloadStatus = computed(() => props.item.download_status ?? "");

const detailTo = computed(() => {
  if (props.source === "online" && props.item.gid && props.item.token) {
    return { name: "online-detail", params: { gid: props.item.gid, token: props.item.token } };
  }
  return { name: "gallery", params: { id: props.item.id } };
});

const ariaLabel = computed(
  () => `${props.item.title} (${categoryBadge.value.label}, ${props.item.page_count}P)`,
);

const tagSource = computed<TagSource>(
  () => props.tagSource ?? (props.source === "online" ? "online" : "local"),
);
const tagNavigation = useTagNavigation(tagSource.value);

const menu = ref<TagMenuEvent | null>(null);
const compact = ref(false);
const maxTags = computed(() => (compact.value ? 3 : 4));

let media: MediaQueryList | null = null;

function syncCompact(event?: MediaQueryListEvent): void {
  compact.value = event ? event.matches : Boolean(media?.matches);
}

onMounted(() => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  media = window.matchMedia("(max-width: 599px)");
  syncCompact();
  media.addEventListener?.("change", syncCompact);
});

onBeforeUnmount(() => media?.removeEventListener?.("change", syncCompact));

function onTagSelect(tag: TagLike): void {
  void tagNavigation.navigate(tag);
}

function onTagExclude(tag: TagLike): void {
  void tagNavigation.navigate(tag, { exclude: true });
}
</script>

<template>
  <article
    class="gallery-list-row"
    :class="{ 'gallery-list-row--selected': selected }"
    data-testid="gallery-list-row"
    :data-id="item.id"
  >
    <RouterLink
      class="gallery-list-row__link"
      :to="detailTo"
      :aria-label="ariaLabel"
      @click="$emit('open', item)"
    />

    <div v-if="selectable" class="gallery-list-row__select" data-corner="select">
      <Checkbox
        :model-value="selected"
        :aria-label="`${t('collection.table.select')} ${item.title}`"
        @update:model-value="$emit('select', item.id, $event)"
      />
    </div>

    <div class="gallery-list-row__cover">
      <img
        v-if="coverSrc"
        class="gallery-list-row__image"
        :src="coverSrc"
        :alt="item.title"
        loading="lazy"
        decoding="async"
      />
      <div v-else class="gallery-list-row__placeholder" aria-hidden="true">
        <span>{{ t("legacy.noCover") }}</span>
      </div>
      <div v-if="progress" class="gallery-list-row__progress" aria-hidden="true">
        <span
          class="gallery-list-row__progress-fill"
          :style="{ width: `${progress.percent}%` }"
        />
      </div>
    </div>

    <div class="gallery-list-row__body">
      <h3 class="gallery-list-row__title">{{ item.title }}</h3>
      <p v-if="showMeta" class="gallery-list-row__sub" :title="subLine">{{ subLine }}</p>

      <TagList
        v-if="tagCount > 0"
        class="gallery-list-row__tags"
        :tags="tags"
        :tag-count="tagCount"
        :max="maxTags"
        :size="24"
        :source="source"
        @select="onTagSelect"
        @exclude="onTagExclude"
        @menu="menu = $event"
      />

      <div class="gallery-list-row__bottom">
        <BadgeStrip :badges="rowBadges" :max="4" data-testid="list-badges" />
        <span class="gallery-list-row__pages" data-testid="list-pages">{{ pagesText }}</span>
        <span class="gallery-list-row__rating" :title="ratingLabel" :aria-label="ratingLabel">
          <Icon
            :name="typeof item.rating === 'number' && item.rating > 0 ? 'star' : 'star-empty'"
            size="sm"
            aria-hidden="true"
          />
          <span>{{ ratingText }}</span>
        </span>
        <span class="gallery-list-row__size">{{ sizeText }}</span>

        <span class="gallery-list-row__states">
          <span
            class="gallery-list-row__state"
            :class="{ 'gallery-list-row__state--on': favorited }"
            :title="favorited ? t('collection.status.favorited') : t('collection.status.notFavorited')"
            :aria-label="favorited ? t('collection.status.favorited') : t('collection.status.notFavorited')"
            data-testid="list-status-favorite"
            role="img"
          >
            <Icon :name="favorited ? 'favorite' : 'favorite-outline'" size="sm" aria-hidden="true" />
          </span>
          <span
            v-if="inLibrary"
            class="gallery-list-row__state gallery-list-row__state--on"
            :title="t('collection.status.inLibrary')"
            :aria-label="t('collection.status.inLibrary')"
            data-testid="list-status-library"
            role="img"
          >
            <Icon name="library" size="sm" aria-hidden="true" />
          </span>
          <span
            v-if="downloadStatus && downloadStatus !== 'none'"
            class="gallery-list-row__state gallery-list-row__state--on"
            :title="t('collection.status.download')"
            :aria-label="`${t('collection.status.download')}: ${downloadStatus}`"
            data-testid="list-status-download"
            role="img"
          >
            <Icon name="downloads" size="sm" aria-hidden="true" />
          </span>
        </span>
      </div>
    </div>

    <div v-if="$slots.actions" class="gallery-list-row__actions">
      <slot name="actions" :item="item" />
    </div>

    <TagMenu
      v-if="menu"
      :tag="menu.tag"
      :x="menu.x"
      :y="menu.y"
      :source="tagSource"
      @close="menu = null"
      @copied="menu = null"
    />
  </article>
</template>

<style scoped>
.gallery-list-row {
  position: relative;
  display: flex;
  gap: var(--gv-space-3);
  align-items: stretch;
  height: var(--gv-size-list-row);
  padding: var(--gv-space-3);
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
  transition: background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.gallery-list-row:hover {
  background: var(--gv-color-surface-container-high);
}

.gallery-list-row--selected {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

.gallery-list-row__link {
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: var(--gv-radius-md);
}

.gallery-list-row__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.gallery-list-row__select {
  position: relative;
  z-index: 3;
  display: flex;
  flex: none;
  align-items: flex-start;
  pointer-events: auto;
}

.gallery-list-row__cover {
  position: relative;
  flex: none;
  width: 96px;
  height: 128px;
  overflow: hidden;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
  pointer-events: none;
}

.gallery-list-row__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.gallery-list-row__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  text-align: center;
}

.gallery-list-row__progress {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: var(--gv-space-1);
  background: var(--gv-color-outline-variant);
}

.gallery-list-row__progress-fill {
  display: block;
  height: 100%;
  background: var(--gv-color-primary);
}

.gallery-list-row__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
  overflow: hidden;
  pointer-events: none;
}

.gallery-list-row__title {
  display: -webkit-box;
  min-height: calc(var(--gv-type-title-small-line) * 2);
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  overflow-wrap: anywhere;
}

.gallery-list-row__sub {
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-list-row__tags {
  position: relative;
  z-index: 3;
  min-height: var(--gv-size-tag);
  pointer-events: auto;
}

.gallery-list-row__bottom {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
  margin-top: auto;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.gallery-list-row__pages,
.gallery-list-row__size,
.gallery-list-row__rating {
  flex: none;
  white-space: nowrap;
}

.gallery-list-row__rating {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  min-width: var(--gv-space-6);
  color: var(--gv-color-warning);
}

.gallery-list-row__states {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  margin-inline-start: auto;
  color: var(--gv-color-on-surface-variant);
}

.gallery-list-row__state {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.gallery-list-row__state--on {
  color: var(--gv-color-primary-text);
}

.gallery-list-row__actions {
  position: relative;
  z-index: 3;
  display: flex;
  flex: none;
  align-self: center;
  align-items: center;
  pointer-events: auto;
}

@media (max-width: 599.98px) {
  .gallery-list-row {
    gap: var(--gv-space-2);
    padding: var(--gv-space-2);
  }

  .gallery-list-row__select {
  position: relative;
  z-index: 3;
  display: flex;
  flex: none;
  align-items: flex-start;
  pointer-events: auto;
}

.gallery-list-row__cover {
    width: 80px;
    height: 107px;
  }

  .gallery-list-row__body {
    gap: 3px;
  }

  .gallery-list-row__bottom {
    gap: var(--gv-space-1);
  }
}
</style>
