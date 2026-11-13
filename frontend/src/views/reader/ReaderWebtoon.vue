<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ReaderPage from "./ReaderPage.vue";
import {
  buildWebtoonOffsets,
  computeWebtoonWindow,
  webtoonPageAt,
  type ReaderFit,
} from "@/reader/pure";

const props = defineProps<{
  total: number;
  currentPage: number;
  fit: ReaderFit;
  failedPages: ReadonlySet<number>;
  retryNonce: Record<number, number>;
  urlFor: (page: number) => string | null;
  placeholderFor: (page: number) => string;
  retryLabel: string;
  altFor: (page: number) => string;
}>();

const emit = defineEmits<{
  load: [info: { page: number; width: number; height: number }];
  error: [page: number];
  retry: [page: number];
  pageChange: [page: number];
}>();

const scroller = ref<HTMLElement | null>(null);
const scrollTop = ref(0);
const viewportHeight = ref(800);
const viewportWidth = ref(640);
const ratios = ref<Record<number, number>>({});
const failedHeight = 320;
let lastEmitted = -1;
let resizeObserver: ResizeObserver | null = null;

const estimatedHeight = computed(() => Math.max(320, Math.round(viewportWidth.value * 1.4)));

const heights = computed<Record<number, number>>(() => {
  const out: Record<number, number> = {};
  for (let page = 0; page < props.total; page += 1) {
    if (props.failedPages.has(page)) {
      out[page] = failedHeight;
      continue;
    }
    const ratio = ratios.value[page];
    out[page] =
      Number.isFinite(ratio) && ratio > 0
        ? Math.max(80, Math.round(ratio * viewportWidth.value))
        : estimatedHeight.value;
  }
  return out;
});

const offsets = computed(() =>
  buildWebtoonOffsets(props.total, heights.value, estimatedHeight.value),
);
const totalHeight = computed(() => offsets.value[props.total] ?? 0);
const range = computed(() =>
  computeWebtoonWindow(
    offsets.value,
    props.total,
    scrollTop.value,
    viewportHeight.value,
    4,
    22,
  ),
);
const visiblePages = computed(() => {
  const pages: number[] = [];
  for (let page = range.value.start; page < range.value.end; page += 1) pages.push(page);
  return pages;
});

function measureViewport(): void {
  const element = scroller.value;
  if (!element) return;
  viewportHeight.value = Math.max(1, element.clientHeight || window.innerHeight || 800);
  viewportWidth.value = Math.max(1, element.clientWidth || window.innerWidth || 640);
}

function onScroll(): void {
  const element = scroller.value;
  if (!element) return;
  scrollTop.value = element.scrollTop;
  const page = webtoonPageAt(
    offsets.value,
    props.total,
    element.scrollTop,
    viewportHeight.value,
  );
  if (page !== lastEmitted) {
    lastEmitted = page;
    emit("pageChange", page);
  }
}

function scrollToPage(page: number, smooth = false): void {
  const element = scroller.value;
  if (!element) return;
  const target = offsets.value[Math.max(0, Math.min(props.total - 1, page))] ?? 0;
  if (typeof element.scrollTo === "function") {
    element.scrollTo({ top: target, behavior: smooth ? "smooth" : "auto" });
  } else {
    element.scrollTop = target;
  }
  scrollTop.value = target;
  lastEmitted = page;
}

function scrollBy(delta: number): void {
  const element = scroller.value;
  if (!element) return;
  element.scrollTop = Math.max(0, element.scrollTop + delta);
  onScroll();
}

function onLoad(info: { page: number; width: number; height: number }): void {
  if (info.width > 0 && info.height > 0) {
    ratios.value = { ...ratios.value, [info.page]: info.height / info.width };
  }
  // Heights are measured after mount, so the initial jump used estimated
  // offsets. Re-anchor the current page once its real height is known.
  if (info.page === props.currentPage) {
    void nextTick(() => scrollToPage(props.currentPage));
  }
  emit("load", info);
}

watch(
  () => props.currentPage,
  (page) => {
    if (page !== lastEmitted) void nextTick(() => scrollToPage(page));
  },
);

watch(
  () => props.total,
  () => void nextTick(() => scrollToPage(props.currentPage)),
);

onMounted(() => {
  measureViewport();
  if (typeof ResizeObserver !== "undefined" && scroller.value) {
    resizeObserver = new ResizeObserver(() => measureViewport());
    resizeObserver.observe(scroller.value);
  }
  void nextTick(() => scrollToPage(props.currentPage));
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
});

defineExpose({ scrollToPage, scrollBy, scrollTop: () => scrollTop.value });
</script>

<template>
  <div
    ref="scroller"
    class="webtoon"
    data-testid="webtoon-strip"
    @scroll.passive="onScroll"
  >
    <div class="webtoon__inner" :style="{ height: `${totalHeight}px` }">
      <div
        v-for="page in visiblePages"
        :key="`${page}:${retryNonce[page] ?? 0}`"
        class="webtoon__item"
        :style="{
          height: `${heights[page] ?? estimatedHeight}px`,
          transform: `translateY(${offsets[page] ?? 0}px)`,
        }"
      >
        <ReaderPage
          :page="page"
          :src="urlFor(page)"
          :fit="fit"
          :alt="altFor(page)"
          :failed="failedPages.has(page)"
          :placeholder="placeholderFor(page)"
          :retry-label="retryLabel"
          @load="onLoad"
          @error="emit('error', $event)"
          @retry="emit('retry', $event)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.webtoon {
  position: absolute;
  inset: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--gv-color-reader-surface);
  touch-action: pan-y;
}

.webtoon__inner {
  position: relative;
  width: 100%;
}

.webtoon__item {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  overflow: hidden;
}
</style>
