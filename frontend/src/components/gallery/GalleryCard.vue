<script setup lang="ts">
/**
 * Gallery card for the three collection views.
 *
 * `variant="grid"` renders the fixed 3:4 cover card: four independent corners
 * (selection / category / pages / actions) that never overlap, the two-line
 * title and one meta line that keeps size + date visible (audit BR-07). Tags
 * are not inline; they appear in a floating panel on hover / keyboard focus
 * and in a bottom sheet on touch long-press (BR-08, PLAN §P6).
 *
 * `variant="list"` delegates to GalleryListRow so the legacy list callers keep
 * working while sharing the new row design.
 */
import { computed, onBeforeUnmount, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import BadgeStrip, { type GalleryBadge } from "./BadgeStrip.vue";
import GalleryListRow from "./GalleryListRow.vue";
import { ensureCollectionMessages } from "./collection-messages";
import { useTagNavigation, type TagSource } from "@/components/tags/useTagNavigation";
import TagList from "@/components/tags/TagList.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import { type TagLike, type TagMenuEvent } from "@/components/tags/tag-utils";
import Checkbox from "@/components/ui/Checkbox.vue";
import Icon from "@/components/icons/Icon.vue";
import Sheet from "@/components/ui/Sheet.vue";
import { formatBytes, formatDate, progressPercent } from "@/stores/library";
import type { GalleryItem } from "@/api/library";

ensureCollectionMessages();

const props = withDefaults(
  defineProps<{
    item: GalleryItem;
    /** `grid` = cover grid, `list` = cover left / info right (legacy API). */
    variant?: "grid" | "list";
    source?: "local" | "online";
    /** Optional override for the top-right badge strip / list badge row. */
    badges?: GalleryBadge[];
    /** Hide meta line when the caller already renders it elsewhere. */
    showMeta?: boolean;
    /** Live favourite state from the shared store, overriding the list payload. */
    favorited?: boolean;
    /** Render the corner selection control (library batch mode). */
    selectable?: boolean;
    selected?: boolean;
    /** Where tag clicks go; defaults to the gallery source. */
    tagSource?: TagSource;
  }>(),
  {
    variant: "grid",
    source: "local",
    badges: undefined,
    showMeta: true,
    favorited: undefined,
    selectable: false,
    selected: false,
    tagSource: undefined,
  },
);

const emit = defineEmits<{
  open: [item: GalleryItem];
  select: [id: number, selected: boolean];
}>();

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

const topBadges = computed<GalleryBadge[]>(() =>
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

const uploader = computed(() => props.item.uploader?.trim() ?? "");
const sizeText = computed(() => formatBytes(props.item.file_size));
const dateText = computed(() => formatDate(props.item.posted_at));

const progress = computed(() => {
  const current = props.item.reading_progress ?? 0;
  if (current <= 0 || props.item.page_count <= 0) return null;
  return {
    current,
    total: props.item.page_count,
    percent: progressPercent(current, props.item.page_count),
  };
});

const pagesBadge = computed(() => {
  if (progress.value) {
    return t("collection.grid.progress", {
      current: progress.value.current,
      total: progress.value.total,
    });
  }
  if (props.item.page_count > 0) {
    return t("collection.grid.pages", { count: props.item.page_count });
  }
  return "";
});

const tags = computed<TagLike[]>(() => props.item.tags ?? []);
const tagCount = computed(() => props.item.tag_count ?? tags.value.length);
const hasTags = computed(() => tagCount.value > 0);

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

const tagSource = computed<TagSource>(
  () => props.tagSource ?? (props.source === "online" ? "online" : "local"),
);
const tagNavigation = useTagNavigation(tagSource.value);

/* ------------------------------------------------------------ interactions */

const hovered = ref(false);
const focusWithin = ref(false);
const sheetOpen = ref(false);
const menu = ref<TagMenuEvent | null>(null);
const suppressClick = ref(false);

const tagsOpen = computed(
  () => props.variant === "grid" && hasTags.value && (hovered.value || focusWithin.value),
);

function onFocusOut(event: FocusEvent): void {
  const next = event.relatedTarget;
  const root = event.currentTarget as HTMLElement | null;
  if (next instanceof Node && root?.contains(next)) return;
  focusWithin.value = false;
}

function onSelect(next: boolean): void {
  emit("select", props.item.id, next);
}

function onTagSelect(tag: TagLike): void {
  void tagNavigation.navigate(tag);
}

function onTagExclude(tag: TagLike): void {
  void tagNavigation.navigate(tag, { exclude: true });
}

function onTagMenu(event: TagMenuEvent): void {
  menu.value = event;
}

function onCardClick(event: MouseEvent): void {
  if (!suppressClick.value) {
    emit("open", props.item);
    return;
  }
  suppressClick.value = false;
  event.preventDefault();
}

/* Touch long-press opens the tag sheet; the following click must not navigate. */
const LONG_PRESS_MS = 500;
let pressTimer: ReturnType<typeof setTimeout> | null = null;
let pressX = 0;
let pressY = 0;

function clearPress(): void {
  if (pressTimer !== null) {
    clearTimeout(pressTimer);
    pressTimer = null;
  }
}

function onPointerDown(event: PointerEvent): void {
  if (props.variant !== "grid" || event.pointerType !== "touch" || !hasTags.value) return;
  clearPress();
  pressX = event.clientX;
  pressY = event.clientY;
  pressTimer = setTimeout(() => {
    pressTimer = null;
    suppressClick.value = true;
    sheetOpen.value = true;
  }, LONG_PRESS_MS);
}

function onPointerMove(event: PointerEvent): void {
  if (pressTimer === null) return;
  if (Math.abs(event.clientX - pressX) > 10 || Math.abs(event.clientY - pressY) > 10) {
    clearPress();
  }
}

onBeforeUnmount(clearPress);
</script>

<template>
  <div
    v-if="variant === 'list'"
    class="gallery-card-list"
    data-testid="gallery-card"
    :data-id="item.id"
  >
    <GalleryListRow
      :item="item"
      :source="source"
      :badges="badges"
      :show-meta="showMeta"
      :favorited="favorited"
      :selectable="selectable"
      :selected="selected"
      :tag-source="tagSource"
      @open="$emit('open', item)"
      @select="(id, next) => emit('select', id, next)"
    >
      <template v-if="$slots.actions" #actions>
        <slot name="actions" :item="item" />
      </template>
    </GalleryListRow>
  </div>

  <article
    v-else
    class="gallery-card"
    :class="[
      `gallery-card--${source}`,
      { 'gallery-card--selected': selected, 'gallery-card--selectable': selectable },
    ]"
    data-testid="gallery-card"
    :data-id="item.id"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
    @focusin="focusWithin = true"
    @focusout="onFocusOut"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="clearPress"
    @pointercancel="clearPress"
    @pointerleave="clearPress"
  >
    <RouterLink
      class="gallery-card__link"
      :to="detailTo"
      :aria-label="ariaLabel"
      @click="onCardClick"
    />

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

      <div
        class="gallery-card__corner gallery-card__corner--start"
        :class="{ 'gallery-card__corner--select': selectable || $slots.selection }"
        :data-corner="selectable || $slots.selection ? 'select' : 'status'"
      >
        <slot v-if="selectable || $slots.selection" name="selection" :item="item">
          <Checkbox
            :model-value="selected"
            :aria-label="`${t('collection.table.select')} ${item.title}`"
            @update:model-value="onSelect"
          />
        </slot>
        <span
          v-else
          class="gallery-card__status"
          :title="progress ? t('collection.status.read') : t('collection.status.unread')"
          :aria-label="progress ? t('collection.status.read') : t('collection.status.unread')"
          data-testid="card-read-state"
          role="img"
        >
          <Icon
            v-if="progress"
            name="visibility"
            size="sm"
            aria-hidden="true"
          />
          <span v-else class="gallery-card__status-dot" aria-hidden="true" />
        </span>
      </div>

      <BadgeStrip
        class="gallery-card__corner gallery-card__corner--end"
        data-corner="category"
        :badges="topBadges"
        align="end"
      />

      <span v-if="pagesBadge" class="gallery-card__pages" data-corner="pages">
        {{ pagesBadge }}
      </span>

      <div v-if="$slots.actions" class="gallery-card__actions" data-corner="actions">
        <slot name="actions" :item="item" />
      </div>

      <div
        v-if="tagsOpen"
        class="gallery-card__tag-overlay"
        :aria-label="t('collection.tags.overlayLabel')"
        data-testid="card-tag-overlay"
      >
        <TagList
          :tags="tags"
          :tag-count="tagCount"
          :max="6"
          :size="24"
          :source="source"
          @select="onTagSelect"
          @exclude="onTagExclude"
          @menu="onTagMenu"
        />
      </div>

      <div v-if="progress" class="gallery-card__progress" aria-hidden="true">
        <span class="gallery-card__progress-fill" :style="{ width: `${progress.percent}%` }" />
      </div>
    </div>

    <div class="gallery-card__body">
      <h3 class="gallery-card__title">{{ item.title }}</h3>
      <p v-if="showMeta" class="gallery-card__meta">
        <span class="gallery-card__meta-name">
          {{ uploader || t("collection.list.empty") }}
        </span>
        <span class="gallery-card__meta-facts">
          <span class="gallery-card__meta-size">
            {{ sizeText || t("collection.list.empty") }}
          </span>
          <span class="gallery-card__meta-date">
            {{ dateText || t("collection.list.empty") }}
          </span>
        </span>
      </p>
    </div>

    <Sheet
      :open="sheetOpen"
      :title="t('collection.tags.sheetTitle')"
      testid="card-tag-sheet"
      @close="sheetOpen = false"
    >
      <TagList
        :tags="tags"
        :tag-count="tagCount"
        :max="Math.max(tagCount, tags.length)"
        :size="28"
        :source="source"
        @select="onTagSelect"
        @exclude="onTagExclude"
        @menu="onTagMenu"
      />
    </Sheet>

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
.gallery-card-list {
  display: block;
  min-width: 0;
}

.gallery-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
  transition:
    box-shadow var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.gallery-card:hover {
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-2);
}

.gallery-card--selected {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

/* Full-card link overlay: interactive corners sit above it with their own
   pointer-events, so a tag / checkbox click never opens the detail page. */
.gallery-card__link {
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: var(--gv-radius-md);
}

.gallery-card__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.gallery-card__cover {
  position: relative;
  overflow: hidden;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  background: var(--gv-color-surface-container-highest);
  pointer-events: none;
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

/* -------------------------------------------------------------- corners */

.gallery-card__corner {
  position: absolute;
  top: var(--gv-space-1);
  z-index: 3;
  display: flex;
  align-items: center;
  max-width: calc(100% - var(--gv-space-6) - var(--gv-space-2));
  pointer-events: auto;
}

.gallery-card__corner--start {
  left: var(--gv-space-1);
}

/* The selection checkbox only appears in selection mode / hover / a selected
   card; the read-state dot stays visible at rest (DESIGN C02). */
.gallery-card__corner--select {
  opacity: 0;
  transition: opacity var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.gallery-card:hover .gallery-card__corner--select,
.gallery-card:focus-within .gallery-card__corner--select,
.gallery-card--selected .gallery-card__corner--select {
  opacity: 1;
}

.gallery-card__corner--end {
  right: var(--gv-space-1);
}

.gallery-card__corner--end :deep(.badge-strip) {
  pointer-events: none;
}

.gallery-card__status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, var(--gv-color-surface) 78%, transparent);
  color: var(--gv-color-on-surface-variant);
}

.gallery-card__status-dot {
  display: block;
  width: 6px;
  height: 6px;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.gallery-card__pages {
  position: absolute;
  bottom: var(--gv-space-1);
  left: var(--gv-space-1);
  z-index: 3;
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: color-mix(in srgb, var(--gv-color-surface) 78%, transparent);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.gallery-card__actions {
  position: absolute;
  right: var(--gv-space-1);
  bottom: var(--gv-space-1);
  z-index: 3;
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  pointer-events: auto;
}

.gallery-card__actions:empty {
  display: none;
}

.gallery-card__tag-overlay {
  position: absolute;
  top: calc(var(--gv-space-5) + var(--gv-space-2));
  right: var(--gv-space-1);
  left: var(--gv-space-1);
  z-index: 2;
  max-height: calc(100% - var(--gv-space-6) - var(--gv-space-2));
  padding: var(--gv-space-2);
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 96%, transparent);
  box-shadow: var(--gv-elev-2);
  pointer-events: auto;
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
  background: var(--gv-color-primary);
}

/* ----------------------------------------------------------------- body */

.gallery-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2);
  overflow: hidden;
  pointer-events: none;
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

/* BR-07: the author truncates, the size + date never do. */
.gallery-card__meta {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  min-width: 0;
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.gallery-card__meta-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gallery-card__meta-facts {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
}

.gallery-card__meta-size::after {
  content: "·";
  margin-inline-start: var(--gv-space-1);
}

@media (prefers-reduced-motion: reduce) {
  .gallery-card,
  .gallery-card__corner--start {
    transition-duration: 1ms;
  }
}
</style>
