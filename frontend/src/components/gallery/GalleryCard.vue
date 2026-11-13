<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import BadgeStrip, { type GalleryBadge } from "./BadgeStrip.vue";
import { formatBytes, formatDate, progressPercent } from "@/stores/library";
import type { GalleryItem } from "@/api/library";

const props = withDefaults(
  defineProps<{
    item: GalleryItem;
    /** `grid` = cover grid (local library), `list` = cover left / info right. */
    variant?: "grid" | "list";
    source?: "local" | "online";
    /** Optional override for the top-left badge strip. */
    badges?: GalleryBadge[];
    /** Hide meta line when the caller already renders it elsewhere. */
    showMeta?: boolean;
    /** Live favourite state from the shared store, overriding the list payload. */
    favorited?: boolean;
  }>(),
  {
    variant: "grid",
    source: "local",
    badges: undefined,
    showMeta: true,
    favorited: undefined,
  },
);

defineEmits<{ open: [item: GalleryItem] }>();

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

function categoryKey(category: string): string {
  return CATEGORY_KEYS[category] ?? "catMisc";
}

function categoryToken(category: string): string {
  return CATEGORY_TOKENS[category] ?? "--gv-cat-misc";
}

const categoryLabel = computed(() => t(`legacy.${categoryKey(props.item.category)}`));
const categoryBadge = computed<GalleryBadge>(() => ({
  label: categoryLabel.value,
  tone: "category",
  colorToken: categoryToken(props.item.category),
  title: categoryLabel.value,
}));

const startBadges = computed<GalleryBadge[]>(() => {
  if (props.badges) return props.badges;
  const badges: GalleryBadge[] = [categoryBadge.value];
  if (props.favorited ?? props.item.favorite) {
    badges.push({ label: "♥", tone: "primary", title: t("legacy.favcatTag") });
  }
  return badges;
});

const endBadges = computed<GalleryBadge[]>(() => {
  const badges: GalleryBadge[] = [];
  if (props.item.page_count > 0) badges.push({ label: `${props.item.page_count}P` });
  if (props.source === "online" && props.item.image_quality === "original") {
    badges.push({ label: "OR", tone: "tertiary", title: t("legacy.qualityOriginal") });
  }
  return badges;
});

const listBadges = computed<GalleryBadge[]>(() => {
  const badges = [...startBadges.value];
  if (props.item.page_count > 0) badges.push({ label: `${props.item.page_count}P` });
  return badges;
});

const coverSrc = computed(() => {
  const value = props.item.cover_url?.trim() ?? "";
  if (!value) return "";
  if (value.includes("\\")) return "";
  return /^(data:image\/(png|jpeg|gif|webp);base64,|https?:\/\/|\/(?!\/))/i.test(value)
    ? value
    : "";
});

const metaText = computed(() => {
  const parts: string[] = [];
  if (props.item.uploader) parts.push(props.item.uploader);
  const size = formatBytes(props.item.file_size);
  if (size) parts.push(size);
  const posted = formatDate(props.item.posted_at);
  if (posted) parts.push(posted);
  return parts.join(" · ");
});

const progress = computed(() => {
  const current = props.item.reading_progress ?? 0;
  if (current <= 0 || props.item.page_count <= 0) return null;
  return {
    current,
    total: props.item.page_count,
    percent: progressPercent(current, props.item.page_count),
  };
});

const detailTo = computed(() => {
  if (props.source === "online" && props.item.gid && props.item.token) {
    return {
      name: "online-detail",
      params: { gid: props.item.gid, token: props.item.token },
    };
  }
  return { name: "gallery", params: { id: props.item.id } };
});

const ariaLabel = computed(
  () => `${props.item.title} (${categoryLabel.value}, ${props.item.page_count}P)`,
);

const firstTags = computed(() =>
  (props.item.tags ?? []).slice(0, 3).map((tag) => ({
    key: `${tag.namespace ?? ""}:${tag.name}`,
    label: tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name,
  })),
);
</script>

<template>
  <article
    class="gallery-card"
    :class="[`gallery-card--${variant}`, `gallery-card--${source}`]"
    data-testid="gallery-card"
    :data-id="item.id"
  >
    <RouterLink
      class="gallery-card__link"
      :to="detailTo"
      :aria-label="ariaLabel"
      @click="$emit('open', item)"
    >
      <div class="gallery-card__cover">
        <img
          v-if="coverSrc"
          class="gallery-card__image"
          :src="coverSrc"
          :alt="item.title"
          loading="lazy"
          decoding="async"
        />
        <div v-else class="gallery-card__placeholder" aria-hidden="true">
          <span>{{ t("legacy.noCover") }}</span>
        </div>

        <BadgeStrip class="gallery-card__badges gallery-card__badges--start" :badges="startBadges" />
        <BadgeStrip
          v-if="variant === 'grid'"
          class="gallery-card__badges gallery-card__badges--end"
          :badges="endBadges"
          align="end"
        />

        <div v-if="variant === 'grid'" class="gallery-card__hover">
          <span class="gallery-card__read">{{ t("legacy.readNow") }}</span>
        </div>

        <div v-if="progress" class="gallery-card__progress" aria-hidden="true">
          <span class="gallery-card__progress-fill" :style="{ width: `${progress.percent}%` }" />
        </div>
      </div>

      <div class="gallery-card__body">
        <h3 class="gallery-card__title">{{ item.title }}</h3>
        <p v-if="showMeta && metaText" class="gallery-card__meta">{{ metaText }}</p>
        <ul v-if="variant === 'list' && firstTags.length" class="gallery-card__tags">
          <li v-for="tag in firstTags" :key="tag.key" class="gallery-card__tag">{{ tag.label }}</li>
        </ul>
        <div v-if="variant === 'list'" class="gallery-card__bottom">
          <BadgeStrip :badges="listBadges" :max="4" />
          <span v-if="progress" class="gallery-card__progress-text">
            {{ progress.current + 1 }}/{{ progress.total }}
          </span>
          <span v-if="item.rating" class="gallery-card__rating">★ {{ item.rating.toFixed(1) }}</span>
        </div>
      </div>
    </RouterLink>

    <div v-if="$slots.actions" class="gallery-card__actions">
      <slot name="actions" :item="item" />
    </div>
  </article>
</template>

<style scoped>
.gallery-card {
  position: relative;
  min-width: 0;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
  overflow: hidden;
  transition:
    box-shadow var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.gallery-card:hover {
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-2);
}

.gallery-card__link {
  display: block;
  color: inherit;
  text-decoration: none;
}

.gallery-card__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.gallery-card__cover {
  position: relative;
  overflow: hidden;
  background: var(--gv-color-surface-container-highest);
}

.gallery-card--grid .gallery-card__cover {
  aspect-ratio: var(--gv-size-card-cover-aspect);
}

.gallery-card__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.gallery-card__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-height: 96px;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.gallery-card__badges {
  position: absolute;
  top: var(--gv-space-1);
  z-index: 2;
  max-width: calc(100% - var(--gv-space-2));
}

.gallery-card__badges--start {
  left: var(--gv-space-1);
}

.gallery-card__badges--end {
  right: var(--gv-space-1);
}

.gallery-card__hover {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--gv-color-scrim) 42%, transparent);
  opacity: 0;
  transition: opacity var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.gallery-card:hover .gallery-card__hover,
.gallery-card__link:focus-visible .gallery-card__hover {
  opacity: 1;
}

.gallery-card__read {
  padding: var(--gv-space-1) var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
  font: var(--gv-type-label-large);
}

.gallery-card__progress {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 2;
  height: var(--gv-space-1);
  background: var(--gv-color-outline-variant);
}

.gallery-card__progress-fill {
  display: block;
  height: 100%;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.gallery-card__body {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2);
}

.gallery-card__title {
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

.gallery-card__meta {
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-card__actions {
  position: absolute;
  right: var(--gv-space-1);
  bottom: var(--gv-space-1);
  z-index: 3;
  display: flex;
  gap: var(--gv-space-1);
}

.gallery-card__actions:empty {
  display: none;
}

/* ---------------------------------------------------------- list variant */

.gallery-card--list {
  border-radius: var(--gv-radius-md);
}

.gallery-card--list .gallery-card__link {
  display: flex;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3);
}

.gallery-card--list .gallery-card__cover {
  flex: 0 0 104px;
  width: 104px;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  border-radius: var(--gv-radius-sm);
}

.gallery-card--list .gallery-card__body {
  flex: 1;
  min-width: 0;
  padding: 0;
}

.gallery-card--list .gallery-card__title {
  min-height: auto;
  font: var(--gv-type-title-medium);
}

.gallery-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  margin: var(--gv-space-1) 0 0;
  padding: 0;
  overflow: hidden;
  list-style: none;
}

.gallery-card__tag {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.gallery-card__bottom {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  margin-top: auto;
  padding-top: var(--gv-space-1);
}

.gallery-card__progress-text,
.gallery-card__rating {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.gallery-card__rating {
  color: var(--gv-color-warning);
}

@media (prefers-reduced-motion: reduce) {
  .gallery-card,
  .gallery-card__hover {
    transition-duration: 1ms;
  }
}
</style>
