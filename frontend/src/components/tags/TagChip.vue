<script setup lang="ts">
import { computed, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import {
  namespaceLabel,
  tagLabel,
  tagNamespace,
  tagRawText,
  type TagLike,
  type TagMenuEvent,
} from "./tag-utils";
import "./i18n";

/**
 * One tag chip. The visible text is the tag body only; the namespace is
 * carried by a 6px colour dot and by the tooltip / aria-label
 * (`<namespace title>：<raw ns:name>`). It renders a button so it can sit
 * inside a card link without triggering that link.
 */
const props = withDefaults(
  defineProps<{
    tag: TagLike;
    size?: 24 | 28;
  }>(),
  { size: 24 },
);

const emit = defineEmits<{
  select: [tag: TagLike];
  exclude: [tag: TagLike];
  menu: [event: TagMenuEvent];
}>();

const { t, te, locale } = useI18n();

const text = computed(() => tagLabel(props.tag, locale.value));
const raw = computed(() => tagRawText(props.tag));
const namespace = computed(() => tagNamespace(props.tag));
const namespaceTitle = computed(() => {
  const key = `gallery.namespaces.${namespace.value}`;
  if (!te(key)) return namespace.value;
  return namespaceLabel(namespace.value, t);
});
const accessibleTitle = computed(() => `${namespaceTitle.value}：${raw.value}`);
const namespaceStyle = computed(() => ({
  "--gv-tag-ns": `var(--gv-tagns-${namespace.value}, var(--gv-tagns-other))`,
}));

const LONG_PRESS_MS = 500;
let timer: ReturnType<typeof setTimeout> | null = null;
let startX = 0;
let startY = 0;
let suppressClick = false;

function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}

function openMenu(x: number, y: number): void {
  emit("menu", { tag: props.tag, x, y });
}

function onPointerDown(event: PointerEvent): void {
  if (event.pointerType !== "touch") return;
  clearTimer();
  suppressClick = false;
  startX = event.clientX;
  startY = event.clientY;
  timer = setTimeout(() => {
    timer = null;
    suppressClick = true;
    openMenu(event.clientX, event.clientY);
  }, LONG_PRESS_MS);
}

function onPointerMove(event: PointerEvent): void {
  if (timer === null) return;
  if (Math.abs(event.clientX - startX) > 10 || Math.abs(event.clientY - startY) > 10) {
    clearTimer();
  }
}

function onPointerEnd(): void {
  clearTimer();
}

function onContextMenu(event: MouseEvent): void {
  event.preventDefault();
  event.stopPropagation();
  clearTimer();
  openMenu(event.clientX, event.clientY);
}

function onClick(event: MouseEvent): void {
  event.preventDefault();
  event.stopPropagation();
  if (suppressClick) {
    suppressClick = false;
    return;
  }
  if (event.shiftKey || event.ctrlKey || event.metaKey) {
    emit("exclude", props.tag);
    return;
  }
  emit("select", props.tag);
}

onBeforeUnmount(clearTimer);
</script>

<template>
  <button
    type="button"
    class="tag-chip"
    :class="[`tag-chip--${size}`]"
    :title="accessibleTitle"
    :aria-label="accessibleTitle"
    :data-namespace="namespace"
    :data-size="size"
    :style="namespaceStyle"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerEnd"
    @pointercancel="onPointerEnd"
    @pointerleave="onPointerEnd"
    @contextmenu="onContextMenu"
    @click="onClick"
  >
    <span class="tag-chip__dot" aria-hidden="true" />
    <span class="tag-chip__text">{{ text }}</span>
  </button>
</template>

<style scoped>
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  max-width: 100%;
  min-width: 0;
  padding: 0 var(--gv-space-2);
  border: 1px solid transparent;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  transition:
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    border-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.tag-chip--24 {
  height: var(--gv-size-tag);
}

.tag-chip--28 {
  height: var(--gv-size-tag-lg);
}

.tag-chip__dot {
  display: block;
  width: 6px;
  height: 6px;
  flex: none;
  border-radius: var(--gv-radius-full);
  background: var(--gv-tag-ns, var(--gv-tagns-other));
}

.tag-chip__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-chip:hover {
  background: var(--gv-color-surface-container-highest);
  border-color: var(--gv-tag-ns, var(--gv-tagns-other));
}

.tag-chip:active {
  background: var(--gv-color-surface-container-highest);
}

.tag-chip:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}
</style>
