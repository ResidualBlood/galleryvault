<script setup lang="ts">
/**
 * Online list row (DESIGN C03 / C18, audit OL-01 … OL-13).
 *
 * Cover left, then two title lines, `uploader · posted · language`, the first
 * four inline tags with `+N`, and a bottom line with category, pages, rating,
 * library/download state and an always-visible favourite + download action.
 * Language is inferred from the `language:*` tag and is omitted when absent.
 * Missing values render an em dash so the row never opens a vertical hole.
 */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import BadgeStrip, { type GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
import TagList from "@/components/tags/TagList.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import { type TagLike, type TagMenuEvent } from "@/components/tags/tag-utils";
import Icon from "@/components/icons/Icon.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import FavButton from "@/components/actions/FavButton.vue";
import DownloadButton from "@/components/actions/DownloadButton.vue";
import { formatDate } from "@/stores/library";
import { inlineTags, languageLabel } from "./helpers";
import type { GalleryItem } from "@/api/library";

const props = withDefaults(
  defineProps<{
    item: GalleryItem;
    selected?: boolean;
    tagMax?: number;
  }>(),
  { selected: false, tagMax: 4 },
);

const emit = defineEmits<{
  select: [id: number, selected: boolean];
  tag: [tag: TagLike];
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

const empty = computed(() => t("collection.list.empty"));

const categoryBadge = computed<GalleryBadge>(() => {
  const label = t(`legacy.${CATEGORY_LABELS[props.item.category] ?? "catMisc"}`);
  return {
    label,
    tone: "category",
    colorToken: CATEGORY_TOKENS[props.item.category] ?? "--gv-cat-misc",
    title: label,
  };
});

const coverSrc = computed(() => {
  const value = props.item.cover_url?.trim() ?? "";
  if (!value) return "";
  if (value.includes("\\")) return "";
  return /^(data:image\/(png|jpeg|gif|webp);base64,|https?:\/\/|\/(?!\/))/i.test(value)
    ? value
    : "";
});

const detailTo = computed(() => ({
  name: "online-detail",
  params: { gid: props.item.gid, token: props.item.token },
}));

const tags = computed<TagLike[]>(() => props.item.tags ?? []);
const visibleTags = computed<TagLike[]>(() => inlineTags(tags.value));

const language = computed(() => languageLabel(tags.value, locale.value));
const uploader = computed(() => props.item.uploader?.trim() || empty.value);
const dateText = computed(() => formatDate(props.item.posted_at) || empty.value);
const subLine = computed(() => {
  const parts = [uploader.value, dateText.value];
  if (language.value) parts.push(language.value);
  return parts.join(" · ");
});

const pagesText = computed(() =>
  props.item.page_count > 0
    ? t("collection.list.pages", { count: props.item.page_count })
    : empty.value,
);
const ratingText = computed(() =>
  typeof props.item.rating === "number" && props.item.rating > 0
    ? props.item.rating.toFixed(1)
    : empty.value,
);
const ratingLabel = computed(() =>
  typeof props.item.rating === "number" && props.item.rating > 0
    ? t("collection.rating.label", { value: props.item.rating.toFixed(1) })
    : t("collection.rating.none"),
);

const inLibrary = computed(() => Boolean(props.item.in_library));
const inLibraryLabel = computed(() =>
  props.item.in_library ? t("online.badges.inLibrary") : "",
);

const downloadText = computed(() => {
  switch ((props.item.download_status ?? "").toLowerCase()) {
    case "downloading":
      return t("online.badges.downloading");
    case "pending":
    case "queued":
      return t("online.badges.queued");
    case "failed":
    case "error":
      return t("online.badges.failed");
    default:
      return "";
  }
});

const menu = ref<TagMenuEvent | null>(null);

function onTagSelect(tag: TagLike): void {
  emit("tag", tag);
}
</script>

<template>
  <article
    class="online-row"
    :class="{ 'online-row--selected': selected }"
    data-testid="gallery-card"
    :data-id="item.id"
    :data-gid="item.gid"
  >
    <RouterLink
      class="online-row__link"
      :to="detailTo"
      :aria-label="`${item.title} (${categoryBadge.label}, ${pagesText})`"
    />

    <div class="online-row__select">
      <Checkbox
        :model-value="selected"
        :aria-label="`${t('collection.table.select')} ${item.title}`"
        @update:model-value="emit('select', item.id, $event)"
      />
    </div>

    <div class="online-row__cover">
      <img
        v-if="coverSrc"
        class="online-row__image"
        :src="coverSrc"
        :alt="item.title"
        loading="lazy"
        decoding="async"
      />
      <div v-else class="online-row__placeholder" aria-hidden="true">
        <span>{{ t("legacy.noCover") }}</span>
      </div>
    </div>

    <div class="online-row__body">
      <h3 class="online-row__title" data-testid="online-row-title">{{ item.title }}</h3>
      <p class="online-row__sub" data-testid="online-row-meta" :title="subLine">
        {{ subLine }}
      </p>

      <TagList
        v-if="visibleTags.length"
        class="online-row__tags"
        :tags="visibleTags"
        :tag-count="visibleTags.length"
        :max="tagMax"
        :size="24"
        source="online"
        @select="onTagSelect"
        @menu="menu = $event"
      />
      <span v-else class="online-row__tags-empty" data-testid="online-row-tags-empty">
        {{ empty }}
      </span>

      <div class="online-row__bottom">
        <BadgeStrip :badges="[categoryBadge]" :max="1" data-testid="online-row-category" />
        <span class="online-row__pages" data-testid="online-row-pages">{{ pagesText }}</span>
        <span
          class="online-row__rating"
          :title="ratingLabel"
          :aria-label="ratingLabel"
          data-testid="online-row-rating"
        >
          <Icon
            :name="typeof item.rating === 'number' && item.rating > 0 ? 'star' : 'star-empty'"
            size="sm"
            aria-hidden="true"
          />
          <span>{{ ratingText }}</span>
        </span>
        <span
          v-if="inLibraryLabel"
          class="online-row__state"
          :title="inLibraryLabel"
          :aria-label="inLibraryLabel"
          data-testid="online-row-library"
        >
          <Icon name="library" size="sm" aria-hidden="true" />
          <span>{{ inLibraryLabel }}</span>
        </span>
        <span
          v-if="downloadText"
          class="online-row__state"
          :title="downloadText"
          :aria-label="downloadText"
          data-testid="online-row-download"
        >
          <Icon name="downloads" size="sm" aria-hidden="true" />
          <span>{{ downloadText }}</span>
        </span>

        <span v-if="item.gid && item.token" class="online-row__actions">
          <FavButton
            :gid="item.gid"
            :token="item.token"
            :favorited="Boolean(item.favorite)"
            :favcat="item.favorite_category ?? null"
            density="card"
          />
          <DownloadButton
            :gid="item.gid"
            :token="item.token"
            :title="item.title"
            :status="item.download_status ?? null"
            :in-library="Boolean(inLibrary)"
            density="card"
          />
        </span>
      </div>
    </div>

    <TagMenu
      v-if="menu"
      :tag="menu.tag"
      :x="menu.x"
      :y="menu.y"
      source="online"
      @close="menu = null"
      @copied="menu = null"
    />
  </article>
</template>

<style scoped>
.online-row {
  position: relative;
  display: flex;
  gap: var(--gv-space-3);
  align-items: stretch;
  height: 100%;
  padding: var(--gv-space-3);
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
  transition: background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.online-row:hover {
  background: var(--gv-color-surface-container-high);
}

.online-row--selected {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

.online-row__link {
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: var(--gv-radius-md);
}

.online-row__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.online-row__select {
  position: absolute;
  top: var(--gv-space-2);
  left: var(--gv-space-2);
  z-index: 4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, var(--gv-color-surface) 82%, transparent);
  box-shadow: var(--gv-elev-1);
}

.online-row__cover {
  position: relative;
  flex: none;
  width: 96px;
  height: 128px;
  overflow: hidden;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
  pointer-events: none;
}

.online-row__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.online-row__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  text-align: center;
}

.online-row__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
  overflow: hidden;
  pointer-events: none;
}

.online-row__title {
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

.online-row__sub {
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.online-row__tags {
  position: relative;
  z-index: 3;
  min-height: var(--gv-size-tag);
  pointer-events: auto;
}

.online-row__tags-empty {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-size-tag);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.online-row__bottom {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
  min-height: var(--gv-size-control-sm);
  margin-top: auto;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.online-row__pages,
.online-row__rating,
.online-row__state {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  white-space: nowrap;
}

.online-row__rating {
  color: var(--gv-color-warning);
}

.online-row__actions {
  position: relative;
  z-index: 3;
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  margin-inline-start: auto;
  pointer-events: auto;
}

@media (max-width: 599.98px) {
  .online-row {
    gap: var(--gv-space-2);
    padding: var(--gv-space-2);
  }

  .online-row__cover {
    width: 80px;
    height: 107px;
  }

  .online-row__body {
    gap: 3px;
  }

  .online-row__bottom {
    gap: var(--gv-space-1);
  }

  .online-row__state span {
    display: none;
  }
}
</style>
