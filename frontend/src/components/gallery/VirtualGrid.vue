<script setup lang="ts">
/**
 * Windowed collection surface shared by every browsing page.
 *
 * Three fixed-row-height variants (DESIGN.md C18):
 *   - `grid`  cover cards, row height = column width * 4/3 + 76 + gutter;
 *   - `list`  one row per gallery, `--gv-size-list-row` (132 below 600px);
 *   - `table` one row per gallery, `--gv-size-table-row`, sticky header.
 *
 * Switching variants keeps the first visible gallery anchored: the previous
 * row height / column count are snapshotted after each render, so the pre-flush
 * watcher can convert the current scroll offset into an item index and back.
 * Infinite scroll and the sentinel keep their previous behaviour.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import GalleryCard from "./GalleryCard.vue";
import GalleryTable from "./GalleryTable.vue";
import GalleryTableRow from "./GalleryTableRow.vue";
import { ensureCollectionMessages } from "./collection-messages";
import type { SortState, TableColumn } from "./table-columns";
import Button from "@/components/ui/Button.vue";
import {
  canAutoRetry,
  collectionRowHeight,
  computeColumnCount,
  computeRowHeight,
  firstVisibleItemIndex,
  GRID_GAP,
  GRID_MIN_CARD_WIDTH,
  scrollTopForItem,
} from "@/stores/library";
import type { GalleryItem } from "@/api/library";

ensureCollectionMessages();

type CollectionVariant = "grid" | "list" | "table";

const props = withDefaults(
  defineProps<{
    items: GalleryItem[];
    loading?: boolean;
    hasMore?: boolean;
    error?: string | null;
    /** Consecutive failed loads, owned by the list store (0..5). */
    failures?: number;
    total?: number;
    variant?: CollectionVariant;
    source?: "local" | "online";
    minCardWidth?: number;
    gap?: number;
    testid?: string;
    columns?: readonly TableColumn[];
    sort?: SortState | null;
    selectable?: boolean;
    selected?: number[];
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
    columns: () => [],
    sort: null,
    selectable: false,
    selected: () => [],
  },
);

const emit = defineEmits<{
  loadMore: [];
  retry: [];
  sort: [column: TableColumn, direction: "asc" | "desc"];
  select: [id: number, selected: boolean];
  open: [item: GalleryItem];
}>();

const { t } = useI18n();

const root = ref<HTMLElement | null>(null);
const canvas = ref<HTMLElement | null>(null);
const sentinel = ref<HTMLElement | null>(null);
const containerWidth = ref(0);
const containerTop = ref(0);
const scrollY = ref(0);
const viewportHeight = ref(0);
const compact = ref(false);
const OVERSCAN_ROWS = 3;

let media: MediaQueryList | null = null;

function syncCompact(event?: MediaQueryListEvent): void {
  compact.value = event ? event.matches : Boolean(media?.matches);
}

const columnCount = computed(() =>
  props.variant === "grid"
    ? computeColumnCount(containerWidth.value, props.minCardWidth, props.gap)
    : 1,
);

const rowHeight = computed(() =>
  collectionRowHeight(
    props.variant,
    containerWidth.value,
    columnCount.value,
    props.gap,
    compact.value,
  ),
);

const gridRowHeight = computed(() =>
  computeRowHeight(containerWidth.value, columnCount.value, props.gap),
);

const rows = computed(() => {
  const out: GalleryItem[][] = [];
  for (let index = 0; index < props.items.length; index += columnCount.value) {
    out.push(props.items.slice(index, index + columnCount.value));
  }
  return out;
});

const canvasHeight = computed(() => {
  if (rows.value.length === 0) return 0;
  const gutter = props.variant === "grid" ? props.gap : 0;
  return rows.value.length * rowHeight.value - gutter;
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

const selectedSet = computed(() => new Set(props.selected));
const activeVariant = computed(() => props.variant);
const isTable = computed(() => props.variant === "table");

const retryBlocked = computed(() => !canAutoRetry(props.failures));

let observer: IntersectionObserver | null = null;
let resizeObserver: ResizeObserver | null = null;
let frame = 0;

/** Last rendered layout, used by the variant switch to keep the anchor. */
let lastLayout = { rowHeight: 0, columns: 1 };

function measure(): void {
  const element = root.value;
  if (!element) return;
  const rect = element.getBoundingClientRect();
  containerWidth.value = rect.width;
  const anchorElement = canvas.value ?? element;
  const anchorRect = anchorElement.getBoundingClientRect();
  containerTop.value = anchorRect.top + window.scrollY;
  scrollY.value = window.scrollY;
  viewportHeight.value = window.innerHeight;
  lastLayout = { rowHeight: rowHeight.value, columns: columnCount.value };
}

function onScroll(): void {
  if (frame) return;
  frame = window.requestAnimationFrame(() => {
    frame = 0;
    scrollY.value = window.scrollY;
  });
}

watch(
  [rowHeight, columnCount, canvasHeight],
  async () => {
    await nextTick();
    lastLayout = { rowHeight: rowHeight.value, columns: columnCount.value };
  },
  { flush: "post" },
);

/**
 * Keep the first visible gallery in place across grid / list / table switches.
 * Runs pre-flush, so `lastLayout` still describes the outgoing view while the
 * new template (and its row height) is about to render.
 */
watch(
  () => props.variant,
  async () => {
    const previous = lastLayout;
    if (!previous.rowHeight) return;
    const anchorItem = firstVisibleItemIndex(
      scrollY.value,
      containerTop.value,
      previous.rowHeight,
      previous.columns,
    );
    await nextTick();
    measure();
    const target = scrollTopForItem(anchorItem, rowHeight.value, columnCount.value, containerTop.value);
    window.scrollTo(0, target);
    scrollY.value = window.scrollY;
  },
);

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
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    media = window.matchMedia("(max-width: 599px)");
    syncCompact();
    media.addEventListener?.("change", syncCompact);
  }
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
  media?.removeEventListener?.("change", syncCompact);
});
</script>

<template>
  <div
    ref="root"
    class="virtual-grid"
    :class="`virtual-grid--${activeVariant}`"
    :data-testid="testid"
    :data-variant="activeVariant"
    :data-loaded="items.length"
    :data-total="total"
    :data-columns="columnCount"
    :data-row-height="gridRowHeight"
    :data-list-row-height="rowHeight"
    :data-loading="loading ? '1' : '0'"
    :data-has-more="hasMore ? '1' : '0'"
    :data-failures="failures"
  >
    <GalleryTable
      v-if="isTable"
      :columns="props.columns"
      :sort="sort"
      :testid="`${testid}-table`"
      @sort="(column, direction) => emit('sort', column, direction)"
    >
      <template #default="{ columns: visible }">
        <div
          ref="canvas"
          class="virtual-grid__canvas"
          :style="{ height: `${canvasHeight}px` }"
        >
          <div
            v-for="row in visibleRows"
            :key="row.index"
            class="virtual-grid__row virtual-grid__row--table"
            :style="{ transform: `translateY(${row.top}px)` }"
          >
            <template v-for="item in row.items" :key="item.id">
              <slot name="row" :item="item" :columns="visible">
                <GalleryTableRow
                  :item="item"
                  :columns="visible"
                  :source="source"
                  :selectable="selectable"
                  :selected="selectedSet.has(item.id)"
                  @select="(id, next) => emit('select', id, next)"
                  @open="(entry) => emit('open', entry)"
                >
                  <template v-if="$slots.actions" #actions>
                    <slot name="actions" :item="item" />
                  </template>
                </GalleryTableRow>
              </slot>
            </template>
          </div>
        </div>
      </template>
    </GalleryTable>

    <div
      v-else
      ref="canvas"
      class="virtual-grid__canvas"
      :style="{ height: `${canvasHeight}px` }"
    >
      <div
        v-for="row in visibleRows"
        :key="row.index"
        class="virtual-grid__row"
        :style="{
          transform: `translateY(${row.top}px)`,
          gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
          gap: `${gap}px`,
        }"
      >
        <template v-for="item in row.items" :key="item.id">
          <slot name="card" :item="item">
            <GalleryCard
              :item="item"
              :variant="activeVariant === 'list' ? 'list' : 'grid'"
              :source="source"
              :selectable="selectable"
              :selected="selectedSet.has(item.id)"
              @select="(id, next) => emit('select', id, next)"
              @open="(entry) => emit('open', entry)"
            >
              <template v-if="$slots.actions" #actions>
                <slot name="actions" :item="item" />
              </template>
            </GalleryCard>
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
      <Button
        v-else-if="error"
        variant="text"
        size="sm"
        icon="retry"
        data-testid="grid-retry"
        @click="retry"
      >
        {{ t("legacy.clickToRetry") }}
      </Button>
      <span v-else-if="!hasMore && items.length" class="virtual-grid__status">
        {{ t("collection.loadedAll") }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.virtual-grid {
  position: relative;
  width: 100%;
  min-width: 0;
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

.virtual-grid__row--table {
  display: block;
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
</style>
