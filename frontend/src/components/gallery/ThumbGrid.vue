<script lang="ts">
export interface ThumbMetrics {
  columns: number;
  cellWidth: number;
  rowHeight: number;
  rows: number;
  totalHeight: number;
}

const THUMB_ASPECT = 4 / 3;
const DEFAULT_GAP = 8;
const DEFAULT_MIN_CELL = 96;

export function computeMetrics(
  width: number,
  count: number,
  minCell = DEFAULT_MIN_CELL,
  gap = DEFAULT_GAP,
): ThumbMetrics {
  const safeWidth = Math.max(minCell, width);
  const columns = Math.max(1, Math.floor((safeWidth + gap) / (minCell + gap)));
  const cellWidth = (safeWidth - gap * (columns - 1)) / columns;
  const rowHeight = cellWidth * THUMB_ASPECT + gap;
  const rows = Math.max(1, Math.ceil(count / columns));
  return {
    columns,
    cellWidth,
    rowHeight,
    rows,
    totalHeight: rows * rowHeight,
  };
}

export function visibleIndexRange(
  scrollTop: number,
  viewportHeight: number,
  metrics: ThumbMetrics,
  count: number,
  overscan = 2,
): { start: number; end: number } {
  if (count <= 0) return { start: 0, end: 0 };
  const firstRow = Math.max(
    0,
    Math.floor(Math.max(0, scrollTop) / metrics.rowHeight) - overscan,
  );
  const lastRow = Math.min(
    metrics.rows - 1,
    Math.ceil((Math.max(0, scrollTop) + Math.max(0, viewportHeight)) / metrics.rowHeight) +
      overscan,
  );
  return {
    start: Math.min(count, firstRow * metrics.columns),
    end: Math.min(count, (lastRow + 1) * metrics.columns),
  };
}
</script>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { galleryThumbUrl, type GalleryPage } from "@/api/gallery";

const props = withDefaults(
  defineProps<{
    galleryId: number;
    pages?: GalleryPage[];
    currentPage?: number;
    minCell?: number;
    hrefFor?: (index: number) => string;
  }>(),
  {
    pages: () => [],
    currentPage: -1,
    minCell: 96,
    hrefFor: undefined,
  },
);

const emit = defineEmits<{ select: [index: number] }>();
const { t } = useI18n();

const root = ref<HTMLElement | null>(null);
const width = ref(600);
const viewportHeight = ref(800);
const scrollTop = ref(0);
const GAP = 8;

const metrics = computed(() =>
  computeMetrics(width.value, props.pages.length, props.minCell, GAP),
);

const range = computed(() =>
  visibleIndexRange(scrollTop.value, viewportHeight.value, metrics.value, props.pages.length),
);

interface VisibleThumb {
  index: number;
  style: Record<string, string>;
}

const visible = computed<VisibleThumb[]>(() => {
  const { columns, cellWidth, rowHeight } = metrics.value;
  const items: VisibleThumb[] = [];
  for (let index = range.value.start; index < range.value.end; index += 1) {
    if (!props.pages[index]) continue;
    const column = index % columns;
    const row = Math.floor(index / columns);
    items.push({
      index,
      style: {
        width: `${cellWidth}px`,
        height: `${cellWidth * THUMB_ASPECT}px`,
        transform: `translate(${column * (cellWidth + GAP)}px, ${row * rowHeight}px)`,
      },
    });
  }
  return items;
});

function defaultHref(index: number): string {
  return `#/reader/${props.galleryId}/${index}`;
}

function measure(): void {
  const element = root.value;
  if (!element) return;
  const rect = element.getBoundingClientRect();
  if (rect.width > 0) width.value = rect.width;
  if (typeof window !== "undefined") {
    const viewport = window.innerHeight || viewportHeight.value;
    viewportHeight.value = viewport;
    const rootTop = rect.top + window.scrollY;
    scrollTop.value = Math.max(0, window.scrollY - rootTop);
  }
}

let frame = 0;
function schedule(): void {
  if (typeof requestAnimationFrame !== "function") {
    measure();
    return;
  }
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    measure();
  });
}

let observer: ResizeObserver | null = null;

onMounted(() => {
  measure();
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
  if (typeof ResizeObserver !== "undefined" && root.value) {
    observer = new ResizeObserver(schedule);
    observer.observe(root.value);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("scroll", schedule);
  window.removeEventListener("resize", schedule);
  observer?.disconnect();
  if (frame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
});
</script>

<template>
  <div
    ref="root"
    class="thumb-grid"
    data-testid="thumb-grid"
    :style="{ height: `${metrics.totalHeight}px` }"
  >
    <a
      v-for="item in visible"
      :key="item.index"
      class="thumb"
      data-testid="thumb"
      :class="{ 'thumb--current': item.index === currentPage }"
      :style="item.style"
      :href="hrefFor ? hrefFor(item.index) : defaultHref(item.index)"
      :aria-current="item.index === currentPage ? 'page' : undefined"
      @click.prevent="emit('select', item.index)"
    >
      <img
        class="thumb__image"
        :src="galleryThumbUrl(galleryId, item.index)"
        :alt="t('gallery.pageLabel', { page: item.index + 1 })"
        loading="lazy"
        decoding="async"
      />
      <span class="thumb__index" aria-hidden="true">{{ item.index + 1 }}</span>
      <span v-if="item.index === currentPage" class="thumb__current">
        {{ t("gallery.current") }}
      </span>
    </a>
  </div>
</template>

<style scoped>
.thumb-grid {
  position: relative;
  width: 100%;
}

.thumb {
  position: absolute;
  top: 0;
  left: 0;
  display: block;
  overflow: hidden;
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-1);
  transition: box-shadow var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.thumb:hover {
  box-shadow: var(--gv-elev-2);
}

.thumb:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.thumb--current {
  outline: 2px solid var(--gv-color-primary);
  outline-offset: -2px;
}

.thumb__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* GD-09: both corner badges share one frosted surface and sit on the same
   baseline (page number bottom-left, "last read" bottom-right), so neither
   covers the middle of the artwork. */
.thumb__index,
.thumb__current {
  position: absolute;
  bottom: var(--gv-space-1);
  max-width: calc(100% - var(--gv-space-2));
  overflow: hidden;
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: color-mix(in srgb, var(--gv-color-surface) 82%, transparent);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thumb__index {
  left: var(--gv-space-1);
}

.thumb__current {
  right: var(--gv-space-1);
}
</style>
