<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import GalleryCard from "./GalleryCard.vue";
import {
  canAutoRetry,
  computeColumnCount,
  computeRowHeight,
  GRID_GAP,
  GRID_MIN_CARD_WIDTH,
} from "@/stores/library";
import type { GalleryItem } from "@/api/library";

const props = withDefaults(
  defineProps<{
    items: GalleryItem[];
    loading?: boolean;
    hasMore?: boolean;
    error?: string | null;
    /** Consecutive failed loads, owned by the list store (0..5). */
    failures?: number;
    total?: number;
    variant?: "grid" | "list";
    source?: "local" | "online";
    minCardWidth?: number;
    gap?: number;
    testid?: string;
  }>(),
  {
    loading: false,
    hasMore: false,
    error: null,
    failures: 0,
    total: 0,
    variant: "grid",
    source: "local",
    minCardWidth: GRID_MIN_CARD_WIDTH,
    gap: GRID_GAP,
    testid: "virtual-grid",
  },
);

const emit = defineEmits<{ loadMore: []; retry: [] }>();
const { t } = useI18n();

const root = ref<HTMLElement | null>(null);
const sentinel = ref<HTMLElement | null>(null);
const containerWidth = ref(0);
const containerTop = ref(0);
const scrollY = ref(0);
const viewportHeight = ref(0);
const OVERSCAN_ROWS = 3;

const columns = computed(() =>
  props.variant === "list"
    ? 1
    : computeColumnCount(containerWidth.value, props.minCardWidth, props.gap),
);

const rowHeight = computed(() =>
  props.variant === "list"
    ? 164
    : computeRowHeight(containerWidth.value, columns.value, props.gap),
);

const rows = computed(() => {
  const out: GalleryItem[][] = [];
  for (let index = 0; index < props.items.length; index += columns.value) {
    out.push(props.items.slice(index, index + columns.value));
  }
  return out;
});

const canvasHeight = computed(() => {
  if (rows.value.length === 0) return 0;
  return rows.value.length * rowHeight.value - props.gap;
});

const visibleRows = computed(() => {
  const rowHeightValue = rowHeight.value;
  if (rowHeightValue <= 0) return [];
  const firstVisible = Math.floor(
    Math.max(0, scrollY.value - containerTop.value) / rowHeightValue,
  );
  const lastVisible = Math.ceil(
    Math.max(0, scrollY.value + (viewportHeight.value || 0) - containerTop.value) /
      rowHeightValue,
  );
  const start = Math.max(0, firstVisible - OVERSCAN_ROWS);
  const end = Math.min(rows.value.length, lastVisible + OVERSCAN_ROWS);
  const out: Array<{ index: number; top: number; items: GalleryItem[] }> = [];
  for (let index = start; index < end; index += 1) {
    out.push({ index, top: index * rowHeightValue, items: rows.value[index] });
  }
  return out;
});

const retryBlocked = computed(() => !canAutoRetry(props.failures));

let observer: IntersectionObserver | null = null;
let resizeObserver: ResizeObserver | null = null;
let frame = 0;

function measure(): void {
  const element = root.value;
  if (!element) return;
  const rect = element.getBoundingClientRect();
  containerWidth.value = rect.width;
  containerTop.value = rect.top + window.scrollY;
  scrollY.value = window.scrollY;
  viewportHeight.value = window.innerHeight;
}

function onScroll(): void {
  if (frame) return;
  frame = window.requestAnimationFrame(() => {
    frame = 0;
    scrollY.value = window.scrollY;
  });
}

function maybeLoadMore(): void {
  if (!props.hasMore || props.loading) return;
  if (props.error && retryBlocked.value) return;
  emit("loadMore");
}

function sentinelInRange(): boolean {
  const element = sentinel.value;
  if (!element) return false;
  const rect = element.getBoundingClientRect();
  return rect.top < window.innerHeight + 900 && rect.bottom > -900;
}

let lastAutoLoadLength = -1;

/**
 * Legacy `startInfinite` keeps pulling pages while the sentinel is in range,
 * because scroll anchoring can keep the sentinel visible after an append.
 * Without this chain the IntersectionObserver never sees a new transition.
 */
function chainIfSentinelVisible(): void {
  if (props.loading || !props.hasMore || props.error) return;
  if (props.items.length === lastAutoLoadLength) return;
  lastAutoLoadLength = props.items.length;
  if (sentinelInRange()) emit("loadMore");
}

watch(
  () => [props.loading, props.items.length, props.hasMore, props.error] as const,
  async () => {
    await nextTick();
    chainIfSentinelVisible();
  },
);

function onIntersect(entries: IntersectionObserverEntry[]): void {
  if (entries.some((entry) => entry.isIntersecting)) maybeLoadMore();
}

function retry(): void {
  emit("retry");
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    maybeLoadMore();
  }
}

onMounted(async () => {
  await nextTick();
  measure();
  chainIfSentinelVisible();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", measure, { passive: true });
  if (typeof ResizeObserver === "function" && root.value) {
    resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(root.value);
  }
  if (typeof IntersectionObserver === "function" && sentinel.value) {
    observer = new IntersectionObserver(onIntersect, { rootMargin: "900px" });
    observer.observe(sentinel.value);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("scroll", onScroll);
  window.removeEventListener("resize", measure);
  if (frame) window.cancelAnimationFrame(frame);
  observer?.disconnect();
  resizeObserver?.disconnect();
});
</script>

<template>
  <div
    ref="root"
    class="virtual-grid"
    :class="`virtual-grid--${variant}`"
    :data-testid="testid"
    :data-loaded="items.length"
    :data-total="total"
    :data-columns="columns"
    :data-row-height="rowHeight"
    :data-loading="loading ? '1' : '0'"
    :data-has-more="hasMore ? '1' : '0'"
    :data-failures="failures"
  >
    <div class="virtual-grid__canvas" :style="{ height: `${canvasHeight}px` }">
      <div
        v-for="row in visibleRows"
        :key="row.index"
        class="virtual-grid__row"
        :style="{
          transform: `translateY(${row.top}px)`,
          gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
          gap: `${gap}px`,
        }"
      >
        <template v-for="item in row.items" :key="item.id">
          <slot name="card" :item="item">
            <GalleryCard :item="item" :variant="variant" :source="source" />
          </slot>
        </template>
      </div>
    </div>

    <div
      ref="sentinel"
      class="virtual-grid__sentinel"
      data-testid="grid-sentinel"
      role="status"
      aria-live="polite"
      tabindex="0"
      @keydown="onKeydown"
    >
      <span v-if="loading" class="virtual-grid__status">{{ t("common.loading") }}</span>
      <button
        v-else-if="error"
        type="button"
        class="virtual-grid__retry"
        data-testid="grid-retry"
        @click="retry"
      >
        ↻ {{ t("legacy.clickToRetry") }}
      </button>
      <span v-else-if="!hasMore && items.length" class="virtual-grid__status">
        {{ t("legacy.noData") }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.virtual-grid {
  position: relative;
  width: 100%;
}

.virtual-grid__canvas {
  position: relative;
  width: 100%;
}

.virtual-grid__row {
  position: absolute;
  top: 0;
  left: 0;
  display: grid;
  width: 100%;
}

.virtual-grid--list .virtual-grid__row {
  grid-template-columns: minmax(0, 1fr);
}

.virtual-grid__sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--gv-size-touch);
  padding: var(--gv-space-2) 0;
}

.virtual-grid__sentinel:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.virtual-grid__status {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.virtual-grid__retry {
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.virtual-grid__retry:hover {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}
</style>
