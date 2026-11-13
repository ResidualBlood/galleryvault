<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import TagChip from "./TagChip.vue";
import {
  sortTagsForInline,
  tagKey,
  type TagLike,
  type TagMenuEvent,
} from "./tag-utils";
import "./i18n";

/**
 * Tag row. It shows up to `max` tags by the inline priority, folds the rest
 * into a `+N` chip and reveals every tag when `+N` is activated. `tagCount`
 * wins over the returned array length, so the backend's truncated
 * `tags_limit` payload still reports the real total.
 *
 * `layout="inline"` (default) keeps the legacy single-line row with an
 * absolutely positioned `+N` overlay. `layout="wrap"` fills its container:
 * chips keep their intrinsic width and wrap onto new lines, and `+N` expands
 * the remaining chips in the same flow (so a parent `overflow` cannot clip
 * them), then collapses them again on the next click.
 */
const props = withDefaults(
  defineProps<{
    tags?: TagLike[];
    max?: number;
    size?: 24 | 28;
    source?: "local" | "online";
    tagCount?: number | null;
    layout?: "inline" | "wrap";
  }>(),
  { tags: () => [], max: 4, size: 24, source: "local", tagCount: null, layout: "inline" },
);

const emit = defineEmits<{
  select: [tag: TagLike];
  exclude: [tag: TagLike];
  menu: [event: TagMenuEvent];
}>();

const { t } = useI18n();
const expanded = ref(false);
const root = ref<HTMLElement | null>(null);

const uniqueTags = computed(() => {
  const seen = new Set<string>();
  const out: TagLike[] = [];
  for (const tag of props.tags) {
    const key = tagKey(tag);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(tag);
  }
  return out;
});

const visible = computed(() =>
  sortTagsForInline(uniqueTags.value).slice(0, Math.max(0, props.max)),
);

const total = computed(() => {
  const known = typeof props.tagCount === "number" ? props.tagCount : 0;
  return Math.max(known, uniqueTags.value.length);
});

const hiddenCount = computed(() => Math.max(0, total.value - visible.value.length));

const moreLabel = computed(() => `+${hiddenCount.value}`);

const hasAny = computed(() => total.value > 0);

const allTags = computed(() => {
  // Overlay keeps language tags too; only inline slots skip them.
  return uniqueTags.value;
});

/** Chips not already in the inline slots, revealed by `+N` in wrap mode. */
const remainingTags = computed(() => {
  const shown = new Set(visible.value.map(tagKey));
  return allTags.value.filter((tag) => !shown.has(tagKey(tag)));
});

const wrapLayout = computed(() => props.layout === "wrap");
const expandedInline = computed(() => wrapLayout.value && expanded.value);

function toggle(): void {
  if (hiddenCount.value <= 0) return;
  expanded.value = !expanded.value;
}

function onDocumentPointer(event: Event): void {
  if (!expanded.value) return;
  const target = event.target;
  if (target instanceof Node && root.value?.contains(target)) return;
  expanded.value = false;
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") expanded.value = false;
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer);
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer);
  document.removeEventListener("keydown", onKeydown);
});

function onSelect(tag: TagLike): void {
  emit("select", tag);
}

function onExclude(tag: TagLike): void {
  emit("exclude", tag);
}

function onMenu(event: TagMenuEvent): void {
  emit("menu", event);
}
</script>

<template>
  <span
    ref="root"
    class="tag-list"
    :class="{ 'tag-list--wrap': wrapLayout }"
    data-testid="tag-list"
    :data-source="source"
    :data-size="size"
    :data-max="max"
    :data-layout="layout"
  >
    <TagChip
      v-for="tag in visible"
      :key="tagKey(tag)"
      :tag="tag"
      :size="size"
      @select="onSelect"
      @exclude="onExclude"
      @menu="onMenu"
    />
    <template v-if="expandedInline">
      <TagChip
        v-for="tag in remainingTags"
        :key="`flow-${tagKey(tag)}`"
        :tag="tag"
        :size="size"
        @select="onSelect"
        @exclude="onExclude"
        @menu="onMenu"
      />
    </template>
    <button
      v-if="hasAny && hiddenCount > 0"
      type="button"
      class="tag-list__more"
      :class="[`tag-list__more--${size}`]"
      data-testid="tag-more"
      :aria-expanded="expanded"
      :aria-label="t('tagsUi.showAll', { count: total })"
      :title="t('tagsUi.showAll', { count: total })"
      @click.stop.prevent="toggle"
    >
      {{ moreLabel }}
    </button>

    <span
      v-if="expanded && !wrapLayout"
      class="tag-list__panel"
      role="group"
      :aria-label="t('tagsUi.allTags')"
      data-testid="tag-list-panel"
      @click.stop
      @contextmenu.prevent.stop
    >
      <TagChip
        v-for="tag in allTags"
        :key="`all-${tagKey(tag)}`"
        :tag="tag"
        :size="size"
        @select="onSelect"
        @exclude="onExclude"
        @menu="onMenu"
      />
    </span>
  </span>
</template>

<style scoped>
.tag-list {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-wrap: nowrap;
  min-width: 0;
  gap: var(--gv-space-1);
  max-width: 100%;
}

/* Wrap layout: chips keep their intrinsic width and flow onto new lines. */
.tag-list--wrap {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
}

.tag-list--wrap :deep(.tag-chip) {
  flex: 0 0 auto;
  max-width: 100%;
}

.tag-list__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  cursor: pointer;
  white-space: nowrap;
}

.tag-list__more--24 {
  height: var(--gv-size-tag);
}

.tag-list__more--28 {
  height: var(--gv-size-tag-lg);
}

.tag-list__more:hover {
  background: var(--gv-color-surface-variant);
}

.tag-list__more:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.tag-list__panel {
  position: absolute;
  top: calc(100% + var(--gv-space-1));
  left: 0;
  z-index: 40;
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  width: max-content;
  max-width: min(360px, calc(100vw - var(--gv-space-6)));
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}
</style>
