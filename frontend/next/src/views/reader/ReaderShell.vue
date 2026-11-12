<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import ReaderTopBar from "./ReaderTopBar.vue";
import ReaderBottomBar from "./ReaderBottomBar.vue";
import ReaderPage from "./ReaderPage.vue";
import ReaderWebtoon from "./ReaderWebtoon.vue";
import ReaderSettingsSheet from "./ReaderSettingsSheet.vue";
import {
  clampReaderScale,
  getReaderNav,
  isDoubleMode,
  isPageFailed,
  isRtlMode,
  markPageFailed,
  normalizeReaderPage,
  pagePlaceholderLabel,
  readerPageKey,
  selectPreloadPages,
  shouldHandleReaderKey,
  type ReaderFit,
  type ReaderMode,
} from "@/reader/pure";
import {
  readReaderFit,
  readReaderMode,
  readSlideshowInterval,
  writeReaderFit,
  writeReaderMode,
  writeSlideshowInterval,
} from "@/reader/storage";
import { ProgressWriter } from "@/reader/progress";
import { PreloadPool } from "@/reader/preload";
import { LocalPageSource } from "@/reader/local-source";
import type { PageSource } from "@/reader/source";
import {
  getNextGallery,
  getReaderGallery,
  saveReaderProgress,
  type ReaderGallery,
} from "@/api/reader";
import { useReaderI18n } from "@/reader/i18n";

const props = withDefaults(
  defineProps<{
    galleryId: number | string;
    initialPage?: number;
    initialMode?: ReaderMode | null;
    initialFit?: ReaderFit | null;
    initialSlideshow?: number | null;
    source?: PageSource | null;
    title?: string;
    fileSize?: number;
    pageCount?: number | null;
  }>(),
  {
    initialPage: 0,
    initialMode: null,
    initialFit: null,
    initialSlideshow: null,
    source: null,
    title: "",
    fileSize: 0,
    pageCount: null,
  },
);

const emit = defineEmits<{
  close: [];
  next: [galleryId: number];
  pageChange: [page: number];
}>();

const { tr } = useReaderI18n();

const stageRef = ref<HTMLElement | null>(null);
const topbarRef = ref<InstanceType<typeof ReaderTopBar> | null>(null);
const webtoonRef = ref<InstanceType<typeof ReaderWebtoon> | null>(null);

const gallery = ref<ReaderGallery | null>(null);
const loading = ref(true);
const loadError = ref("");
const total = ref(0);
const currentPage = ref(0);
const mode = ref<ReaderMode>(props.initialMode ?? readReaderMode());
const fit = ref<ReaderFit>(props.initialFit ?? readReaderFit());
const barsVisible = ref(false);
const settingsOpen = ref(false);
const slideshowOn = ref(false);
const slideshowInterval = ref(readSlideshowInterval());
const nextUnavailable = ref(false);

const urls = ref<Record<number, string>>({});
const retryNonce = ref<Record<number, number>>({});
const pageDims = ref<Record<number, { width: number; height: number }>>({});
const failedVersion = ref(0);
const failedPages = computed<ReadonlySet<number>>(() => {
  void failedVersion.value;
  const set = new Set<number>();
  const now = Date.now();
  for (let page = 0; page < total.value; page += 1) {
    if (isPageFailed(failures, readerPageKey(props.galleryId, page), now)) {
      set.add(page);
    }
  }
  return set;
});

const failures = new Map<string, number>();
const resolving = new Set<number>();
const preloadPageByUrl = new Map<string, number>();
let progress: ProgressWriter | null = null;
let preloader: PreloadPool | null = null;
let hideTimer: ReturnType<typeof setTimeout> | null = null;
let slideshowTimer: ReturnType<typeof setTimeout> | null = null;
let pendingTapTimer: ReturnType<typeof setTimeout> | null = null;
let suppressClick = false;
let lastKeyAt = 0;
let mounted = false;

const source = computed<PageSource>(
  () => props.source ?? new LocalPageSource(props.galleryId, total.value),
);

const nav = computed(() => getReaderNav(currentPage.value, total.value, mode.value));
const displayPages = computed<number[]>(() => {
  if (mode.value === "webtoon") return [currentPage.value];
  const pages = nav.value.pages;
  if (!isDoubleMode(mode.value) || pages.length < 2) return pages;
  const first = pageDims.value[pages[0]];
  const second = pageDims.value[pages[1]];
  const firstWide = Boolean(first && first.width > first.height);
  const secondWide = Boolean(second && second.width > second.height);
  if (secondWide) return [pages[1]];
  if (firstWide) return [pages[0]];
  return pages;
});
const displayLabel = computed(() => {
  if (displayPages.value.length === 2) {
    return tr("spreadOf", {
      from: displayPages.value[0] + 1,
      to: displayPages.value[1] + 1,
      total: total.value,
    });
  }
  return tr("pageOf", { n: currentPage.value + 1, total: total.value });
});
const atEnd = computed(() => {
  if (total.value <= 0) return false;
  if (mode.value === "webtoon") return currentPage.value >= total.value - 1;
  return nav.value.nextPage === null;
});
const galleryTitle = computed(
  () => gallery.value?.title || props.title || tr("title"),
);

const zoomStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
  transformOrigin: `${originX.value}px ${originY.value}px`,
}));

/* --------------------------------------------------------------- loading */

async function loadGallery(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    let data: ReaderGallery | null = null;
    if (props.pageCount === null) {
      data = await getReaderGallery(props.galleryId);
    }
    gallery.value = data;
    const count =
      props.pageCount ??
      (typeof data?.page_count === "number"
        ? data.page_count
        : Array.isArray(data?.pages)
          ? data.pages.length
          : 0);
    total.value = Math.max(0, count);
    currentPage.value = normalizeReaderPage(
      props.initialPage ?? 0,
      total.value,
      mode.value,
    );

    failures.clear();
    failedVersion.value += 1;
    urls.value = {};
    retryNonce.value = {};
    resolving.clear();

    progress?.dispose();
    progress = new ProgressWriter({
      send: (payload) => saveReaderProgress(props.galleryId, payload),
    });
    preloader?.dispose();
    preloader = new PreloadPool({
      limit: 2,
      onError: (url) => {
        const page = preloadPageByUrl.get(url);
        if (page !== undefined) markFailed(page);
      },
    });

    await preparePages();
    if (!mounted) return;
    progress.queue(currentPage.value, total.value, { immediate: true });
    if (props.initialSlideshow && !slideshowOn.value) {
      slideshowInterval.value = writeSlideshowInterval(props.initialSlideshow);
      startSlideshow();
    }
  } catch (error) {
    loadError.value =
      error instanceof Error && error.message ? error.message : tr("loadFailed");
  } finally {
    loading.value = false;
  }
}

function baseUrlFor(page: number): string | null {
  return urls.value[page] ?? null;
}

function urlFor(page: number): string | null {
  const base = baseUrlFor(page);
  if (!base) return null;
  const nonce = retryNonce.value[page];
  if (!nonce) return base;
  return `${base}${base.includes("?") ? "&" : "?"}r=${nonce}`;
}

async function ensurePage(page: number): Promise<void> {
  if (page < 0 || page >= total.value || resolving.has(page)) return;
  if (urls.value[page]) return;
  resolving.add(page);
  try {
    const resolved = await source.value.page(page);
    urls.value = { ...urls.value, [page]: resolved.url };
  } catch {
    markFailed(page);
  } finally {
    resolving.delete(page);
  }
}

async function preparePages(): Promise<void> {
  const wanted = new Set<number>(displayPages.value);
  for (const page of selectPreloadPages(currentPage.value, total.value, mode.value, isFailed)) {
    wanted.add(page);
  }
  if (mode.value === "webtoon") {
    for (let page = currentPage.value - 2; page <= currentPage.value + 12; page += 1) {
      if (page >= 0 && page < total.value) wanted.add(page);
    }
  }
  await Promise.all([...wanted].map((page) => ensurePage(page)));
  if (!preloader) return;
  for (const page of selectPreloadPages(currentPage.value, total.value, mode.value, isFailed)) {
    const url = baseUrlFor(page);
    if (!url) continue;
    preloadPageByUrl.set(url, page);
    preloader.preload([url]);
  }
}

function isFailed(page: number): boolean {
  return isPageFailed(failures, readerPageKey(props.galleryId, page));
}

function markFailed(page: number): void {
  markPageFailed(failures, readerPageKey(props.galleryId, page));
  failedVersion.value += 1;
}

function onPageError(page: number): void {
  if (!isFailed(page)) markFailed(page);
}

function onPageLoad(info: { page: number; width: number; height: number }): void {
  pageDims.value = {
    ...pageDims.value,
    [info.page]: { width: info.width, height: info.height },
  };
  const key = readerPageKey(props.galleryId, info.page);
  if (failures.delete(key)) failedVersion.value += 1;
}

function retryPage(page: number): void {
  failures.delete(readerPageKey(props.galleryId, page));
  retryNonce.value = {
    ...retryNonce.value,
    [page]: (retryNonce.value[page] ?? 0) + 1,
  };
  failedVersion.value += 1;
  void ensurePage(page);
}

/* ------------------------------------------------------------- navigation */

function goToPage(target: number, options: { immediate?: boolean } = {}): void {
  if (total.value <= 0) return;
  const next =
    mode.value === "webtoon"
      ? Math.max(0, Math.min(total.value - 1, Math.floor(target)))
      : normalizeReaderPage(target, total.value, mode.value);
  currentPage.value = next;
  resetZoom();
  if (mode.value === "webtoon" && webtoonRef.value) {
    webtoonRef.value.scrollToPage(next);
  }
  progress?.queue(next, total.value, options.immediate ? { immediate: true } : {});
  void preparePages();
  if (slideshowOn.value) scheduleSlide();
}

function nextPage(): void {
  if (mode.value === "webtoon" && webtoonRef.value) {
    webtoonRef.value.scrollBy(Math.max(200, (stageRef.value?.clientHeight ?? 800) * 0.9));
    return;
  }
  if (nav.value.nextPage !== null) goToPage(nav.value.nextPage);
}

function prevPage(): void {
  if (mode.value === "webtoon" && webtoonRef.value) {
    webtoonRef.value.scrollBy(-Math.max(200, (stageRef.value?.clientHeight ?? 800) * 0.9));
    return;
  }
  if (nav.value.prevPage !== null) goToPage(nav.value.prevPage);
}

function goFirst(): void {
  goToPage(0, { immediate: true });
}

function goLast(): void {
  goToPage(total.value - 1, { immediate: true });
}

function jumpTo(page: number): void {
  goToPage(page, { immediate: true });
}

let preparing = false;
watch(
  () => props.galleryId,
  () => {
    if (mounted) void loadGallery();
  },
);

watch(currentPage, (page) => {
  if (loading.value || total.value === 0) return;
  progress?.queue(page, total.value);
  if (!preparing) {
    preparing = true;
    void preparePages().finally(() => {
      preparing = false;
    });
  }
  if (slideshowOn.value) scheduleSlide();
});

/**
 * The shell stays router-agnostic (the E2E harness mounts it standalone), so
 * the routed wrapper mirrors every committed page into `#/reader/:id/:page`
 * with a history-replacing navigation. Legacy `syncReaderUrl` did the same.
 */
watch(currentPage, (page) => {
  if (total.value <= 0) return;
  emit("pageChange", page);
});

watch(mode, (value) => {
  writeReaderMode(value);
  resetZoom();
  if (value === "webtoon") {
    void nextTick(() => webtoonRef.value?.scrollToPage(currentPage.value));
  } else {
    currentPage.value = normalizeReaderPage(currentPage.value, total.value, value);
  }
  void preparePages();
});

watch(fit, (value) => writeReaderFit(value));

watch(total, () => {
  if (total.value === 0) return;
  currentPage.value = Math.min(currentPage.value, total.value - 1);
});

function setMode(value: ReaderMode): void {
  mode.value = value;
}

function setFit(value: ReaderFit): void {
  fit.value = value;
}


/* --------------------------------------------------------------- the bars */

function clearHideTimer(): void {
  if (hideTimer !== null) clearTimeout(hideTimer);
  hideTimer = null;
}

function scheduleHide(delay = 3_000): void {
  clearHideTimer();
  if (settingsOpen.value) return;
  hideTimer = setTimeout(() => {
    hideTimer = null;
    if (!settingsOpen.value) barsVisible.value = false;
  }, delay);
}

function showBars(): void {
  barsVisible.value = true;
  scheduleHide();
}

function hideBars(): void {
  clearHideTimer();
  barsVisible.value = false;
}

function toggleBars(): void {
  if (barsVisible.value) hideBars();
  else showBars();
}

function openSettings(): void {
  settingsOpen.value = true;
  barsVisible.value = true;
  clearHideTimer();
}

function closeSettings(): void {
  settingsOpen.value = false;
  scheduleHide();
}

/* -------------------------------------------------------------- slideshow */

function startSlideshow(): void {
  slideshowOn.value = true;
  writeSlideshowInterval(slideshowInterval.value);
  scheduleSlide();
}

function stopSlideshow(): void {
  slideshowOn.value = false;
  if (slideshowTimer !== null) clearTimeout(slideshowTimer);
  slideshowTimer = null;
}

function toggleSlideshow(): void {
  if (slideshowOn.value) stopSlideshow();
  else startSlideshow();
}

function scheduleSlide(): void {
  if (slideshowTimer !== null) clearTimeout(slideshowTimer);
  slideshowTimer = null;
  if (!slideshowOn.value) return;
  slideshowTimer = setTimeout(() => {
    slideshowTimer = null;
    if (!slideshowOn.value) return;
    if (nav.value.nextPage !== null) {
      goToPage(nav.value.nextPage, { immediate: true });
    } else {
      stopSlideshow();
      void goNextGallery(true);
    }
  }, slideshowInterval.value * 1_000);
}

function setSlideshowInterval(seconds: number): void {
  slideshowInterval.value = writeSlideshowInterval(seconds);
  if (slideshowOn.value) scheduleSlide();
}

async function goNextGallery(auto = false): Promise<void> {
  try {
    const next = await getNextGallery(props.galleryId);
    if (next && typeof next.id === "number") {
      cancelPendingTap();
      emit("next", next.id);
      return;
    }
    if (auto) stopSlideshow();
    nextUnavailable.value = true;
  } catch {
    if (auto) stopSlideshow();
    nextUnavailable.value = true;
  }
}

/* ------------------------------------------------------------------- zoom */

const scale = ref(1);
const translateX = ref(0);
const translateY = ref(0);
const originX = ref(0);
const originY = ref(0);

function resetZoom(): void {
  scale.value = 1;
  translateX.value = 0;
  translateY.value = 0;
}

function clampTranslate(value: number, dimension: number): number {
  const limit = Math.max(0, ((scale.value - 1) * dimension) / 2 + 48);
  return Math.min(limit, Math.max(-limit, value));
}

function zoomAt(clientX: number, clientY: number): void {
  if (scale.value > 1) {
    resetZoom();
    return;
  }
  const rect = stageRef.value?.getBoundingClientRect();
  if (!rect) return;
  originX.value = clientX - rect.left;
  originY.value = clientY - rect.top;
  scale.value = 2.2;
}

/* --------------------------------------------------------------- gestures */

interface Point {
  x: number;
  y: number;
}

interface GestureState {
  kind: "pending" | "swipe" | "pan" | "pinch";
  startX: number;
  startY: number;
  lastX: number;
  lastY: number;
  startDistance: number;
  startScale: number;
  startTx: number;
  startTy: number;
  moved: boolean;
  captured: boolean;
}

const pointers = new Map<number, Point>();
let gesture: GestureState | null = null;

function isControlTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element || typeof element.closest !== "function") return false;
  return Boolean(
    element.closest(
      "input, a, button, .reader-topbar, .reader-bottombar, .reader-settings, [data-no-gesture]",
    ),
  );
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function onPointerDown(event: PointerEvent): void {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  if (isControlTarget(event.target)) return;
  if (mode.value === "webtoon" && pointers.size === 0) return;
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (pointers.size === 1) {
    gesture = {
      kind: "pending",
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      startDistance: 0,
      startScale: scale.value,
      startTx: translateX.value,
      startTy: translateY.value,
      moved: false,
      captured: false,
    };
  } else if (pointers.size === 2) {
    const points = [...pointers.values()];
    gesture = {
      kind: "pinch",
      startX: (points[0].x + points[1].x) / 2,
      startY: (points[0].y + points[1].y) / 2,
      lastX: 0,
      lastY: 0,
      startDistance: Math.max(1, distance(points[0], points[1])),
      startScale: scale.value,
      startTx: translateX.value,
      startTy: translateY.value,
      moved: true,
      captured: false,
    };
    suppressClick = true;
  }
}

function capturePointer(event: PointerEvent): void {
  if (!gesture || gesture.captured) return;
  gesture.captured = true;
  try {
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  } catch {
    /* synthetic pointers in tests may not be capturable */
  }
}

function onPointerMove(event: PointerEvent): void {
  const point = pointers.get(event.pointerId);
  if (!point || !gesture) return;
  point.x = event.clientX;
  point.y = event.clientY;

  if (gesture.kind === "pinch" && pointers.size >= 2) {
    capturePointer(event);
    const points = [...pointers.values()];
    const factor = distance(points[0], points[1]) / gesture.startDistance;
    scale.value = clampReaderScale(gesture.startScale, factor);
    const rect = stageRef.value?.getBoundingClientRect();
    if (rect) {
      translateX.value = clampTranslate(gesture.startTx, rect.width);
      translateY.value = clampTranslate(gesture.startTy, rect.height);
    }
    suppressClick = true;
    return;
  }

  const dx = event.clientX - gesture.startX;
  const dy = event.clientY - gesture.startY;
  if (scale.value > 1) {
    gesture.kind = "pan";
    gesture.moved = true;
    capturePointer(event);
    const rect = stageRef.value?.getBoundingClientRect();
    if (rect) {
      translateX.value = clampTranslate(gesture.startTx + dx, rect.width);
      translateY.value = clampTranslate(gesture.startTy + dy, rect.height);
    }
    suppressClick = true;
    return;
  }
  if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
    gesture.kind = "swipe";
    gesture.moved = true;
    capturePointer(event);
  }
}

function onPointerUp(event: PointerEvent): void {
  if (!pointers.has(event.pointerId)) return;
  const wasPinch = gesture?.kind === "pinch";
  pointers.delete(event.pointerId);
  if (wasPinch && pointers.size > 0) {
    // Keep the current zoom; the remaining finger becomes a pan anchor.
    gesture = null;
    suppressClick = true;
    return;
  }
  const state = gesture;
  gesture = null;
  if (!state) return;
  if (state.kind === "swipe") {
    const dx = event.clientX - state.startX;
    const dy = event.clientY - state.startY;
    if (Math.abs(dx) >= 50 && Math.abs(dx) > Math.abs(dy) * 1.2) {
      if (dx < 0) {
        if (isRtlMode(mode.value)) prevPage();
        else nextPage();
      } else if (isRtlMode(mode.value)) {
        nextPage();
      } else {
        prevPage();
      }
    }
    suppressClick = true;
  } else if (state.kind === "pan") {
    suppressClick = true;
  }
  if (suppressClick) {
    setTimeout(() => {
      suppressClick = false;
    }, 0);
  }
  if (pointers.size === 0) {
    const element = event.currentTarget as HTMLElement;
    try {
      element.releasePointerCapture?.(event.pointerId);
    } catch {
      /* ignore synthetic pointers */
    }
  }
}

function onPointerCancel(event: PointerEvent): void {
  pointers.delete(event.pointerId);
  gesture = null;
}

/* ------------------------------------------------------------------ taps */

function cancelPendingTap(): void {
  if (pendingTapTimer !== null) clearTimeout(pendingTapTimer);
  pendingTapTimer = null;
}

function runZone(zone: "left" | "center" | "right"): void {
  if (zone === "center") {
    toggleBars();
    return;
  }
  const rtl = isRtlMode(mode.value);
  if (zone === "left") {
    if (rtl) nextPage();
    else prevPage();
  } else if (rtl) {
    prevPage();
  } else {
    nextPage();
  }
}

function onZoneClick(zone: "left" | "center" | "right", event: MouseEvent): void {
  if (suppressClick) return;
  if (event.detail > 1) {
    cancelPendingTap();
    return;
  }
  cancelPendingTap();
  pendingTapTimer = setTimeout(() => {
    pendingTapTimer = null;
    runZone(zone);
  }, 220);
}

function onStageClick(event: MouseEvent): void {
  if (suppressClick || isControlTarget(event.target)) return;
  const rect = stageRef.value?.getBoundingClientRect();
  if (!rect) return;
  const ratio = (event.clientX - rect.left) / rect.width;
  if (ratio < 0.3) onZoneClick("left", event);
  else if (ratio > 0.7) onZoneClick("right", event);
  else onZoneClick("center", event);
}

function onDoubleClick(event: MouseEvent): void {
  if (mode.value === "webtoon") return;
  if (isControlTarget(event.target)) return;
  cancelPendingTap();
  zoomAt(event.clientX, event.clientY);
}

/* ---------------------------------------------------------------- keyboard */

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element) return false;
  const tag = element.tagName?.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    element.isContentEditable
  );
}

function onKeyDown(event: KeyboardEvent): void {
  if (isTypingTarget(event.target)) {
    if (event.key === "Escape") (event.target as HTMLElement).blur();
    return;
  }
  const now = Date.now();
  if (!shouldHandleReaderKey(now, lastKeyAt, event.repeat)) return;
  lastKeyAt = now;

  const rtl = isRtlMode(mode.value);
  let handled = true;
  switch (event.key) {
    case "ArrowLeft":
      if (rtl) nextPage();
      else prevPage();
      break;
    case "ArrowRight":
      if (rtl) prevPage();
      else nextPage();
      break;
    case "ArrowDown":
      if (mode.value === "webtoon") nextPage();
      else handled = false;
      break;
    case "ArrowUp":
      if (mode.value === "webtoon") prevPage();
      else handled = false;
      break;
    case " ":
    case "PageDown":
      nextPage();
      break;
    case "PageUp":
      prevPage();
      break;
    case "Home":
      goFirst();
      break;
    case "End":
      goLast();
      break;
    case "f":
    case "F":
      void toggleFullscreen();
      break;
    case "g":
    case "G":
      topbarRef.value?.focusJump();
      break;
    case "Escape":
      if (settingsOpen.value) closeSettings();
      else hideBars();
      break;
    default:
      handled = false;
  }
  if (handled) event.preventDefault();
}

/* ------------------------------------------------------------- fullscreen */

async function toggleFullscreen(): Promise<void> {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await stageRef.value?.requestFullscreen();
  } catch {
    /* fullscreen can be rejected by the browser; reader keeps working */
  }
}

/* ------------------------------------------------------------------ misc */

function onVisibility(): void {
  if (document.visibilityState === "hidden") progress?.flushNow();
}

function onResize(): void {
  if (mode.value === "webtoon") {
    void nextTick(() => webtoonRef.value?.scrollToPage(currentPage.value));
  }
}

onMounted(() => {
  mounted = true;
  void loadGallery();
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("resize", onResize);
  document.addEventListener("visibilitychange", onVisibility);
});

onBeforeUnmount(() => {
  mounted = false;
  window.removeEventListener("keydown", onKeyDown);
  window.removeEventListener("resize", onResize);
  document.removeEventListener("visibilitychange", onVisibility);
  clearHideTimer();
  stopSlideshow();
  cancelPendingTap();
  progress?.flushNow();
  progress?.dispose();
  preloader?.dispose();
});

defineExpose({
  nextPage,
  prevPage,
  goToPage,
  setMode,
  setFit,
  toggleBars,
  toggleSlideshow,
  currentPage,
  total,
});
</script>

<template>
  <section
    ref="stageRef"
    class="reader"
    :class="{
      'reader--webtoon': mode === 'webtoon',
      'reader--zoom': scale > 1,
    }"
    data-testid="reader-shell"
    :data-page="currentPage"
    :data-total="total"
    :data-mode="mode"
    :data-fit="fit"
    :data-bars="barsVisible ? 'visible' : 'hidden'"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
    @dblclick="onDoubleClick"
    @click="onStageClick"
  >
    <div class="reader__canvas">
      <div
        v-if="loading"
        class="reader__message"
        data-testid="reader-loading"
      >
        {{ tr("loading") }}
      </div>
      <div v-else-if="loadError" class="reader__message" data-testid="reader-error">
        <p>{{ tr("loadFailed") }}</p>
        <button type="button" class="reader__retry" @click="loadGallery">{{ tr("retry") }}</button>
      </div>
      <div v-else-if="total === 0" class="reader__message" data-testid="reader-empty">
        {{ tr("empty") }}
      </div>
      <template v-else>
        <ReaderWebtoon
          v-if="mode === 'webtoon'"
          ref="webtoonRef"
          :total="total"
          :current-page="currentPage"
          :fit="fit"
          :failed-pages="failedPages"
          :retry-nonce="retryNonce"
          :url-for="urlFor"
          :placeholder-for="(page) => pagePlaceholderLabel(page, tr)"
          :retry-label="tr('retry')"
          :alt-for="(page) => tr('page', { n: page + 1 })"
          @load="onPageLoad"
          @error="onPageError"
          @retry="retryPage"
          @page-change="(page) => (currentPage = page)"
        />
        <div v-else class="reader__stage" :style="zoomStyle">
          <div
            class="reader__spread"
            :class="{ 'reader__spread--rtl': mode === 'double-rtl' }"
          >
            <ReaderPage
              v-for="page in displayPages"
              :key="`${page}:${retryNonce[page] ?? 0}`"
              class="reader__page"
              :page="page"
              :src="urlFor(page)"
              :fit="fit"
              :alt="tr('page', { n: page + 1 })"
              :failed="failedPages.has(page)"
              :placeholder="pagePlaceholderLabel(page, tr)"
              :retry-label="tr('retry')"
              @load="onPageLoad"
              @error="onPageError"
              @retry="retryPage"
            />
          </div>
        </div>
      </template>
    </div>

    <div v-if="mode !== 'webtoon' && !loading && !loadError && total > 0" class="reader__zones">
      <button
        type="button"
        class="reader__zone reader__zone--left"
        data-testid="reader-zone-left"
        :aria-label="tr('zonePrev')"
        @click="onZoneClick('left', $event)"
      />
      <button
        type="button"
        class="reader__zone reader__zone--center"
        data-testid="reader-zone-center"
        :aria-label="tr('zoneToggle')"
        @click="onZoneClick('center', $event)"
      />
      <button
        type="button"
        class="reader__zone reader__zone--right"
        data-testid="reader-zone-right"
        :aria-label="tr('zoneNext')"
        @click="onZoneClick('right', $event)"
      />
    </div>

    <div class="reader__bar-layer reader__bar-layer--top" :class="{ 'reader__bar-layer--hidden': !barsVisible }">
      <ReaderTopBar
        ref="topbarRef"
        :title="galleryTitle"
        :page-label="displayLabel"
        :jump-value="currentPage + 1"
        :total="total"
        :jump-label="tr('jump')"
        :jump-hint="tr('jumpHint')"
        :close-label="tr('close')"
        :fullscreen-label="tr('fullscreen')"
        @close="emit('close')"
        @jump="jumpTo"
        @fullscreen="toggleFullscreen"
      />
    </div>

    <div class="reader__bar-layer reader__bar-layer--bottom" :class="{ 'reader__bar-layer--hidden': !barsVisible }">
      <ReaderBottomBar
        :page="currentPage"
        :total="total"
        :page-label="displayLabel"
        :first-label="tr('first')"
        :last-label="tr('last')"
        :settings-label="tr('settings')"
        :slideshow-label="tr(slideshowOn ? 'slideshowStop' : 'slideshowStart')"
        :slideshow-on="slideshowOn"
        :next-label="tr('nextGallery')"
        :at-end="atEnd"
        @first="goFirst"
        @last="goLast"
        @seek="jumpTo"
        @settings="openSettings"
        @slideshow="toggleSlideshow"
        @next="goNextGallery(false)"
        @interaction="showBars"
      />
    </div>

    <ReaderSettingsSheet
      :open="settingsOpen"
      :mode="mode"
      :fit="fit"
      :interval="slideshowInterval"
      :slideshow-on="slideshowOn"
      :title="tr('settings')"
      :mode-label="tr('mode')"
      :fit-label="tr('fit')"
      :slideshow-label="tr('slideshow')"
      :interval-label="tr('slideshowInterval')"
      :close-label="tr('close')"
      :shortcuts="tr('shortcuts')"
      :mode-names="{
        ltr: tr('modes.ltr'),
        rtl: tr('modes.rtl'),
        double: tr('modes.double'),
        'double-rtl': tr('modes.double-rtl'),
        webtoon: tr('modes.webtoon'),
      }"
      :fit-names="{
        height: tr('fits.height'),
        width: tr('fits.width'),
        original: tr('fits.original'),
      }"
      @close="closeSettings"
      @mode="setMode"
      @fit="setFit"
      @interval="setSlideshowInterval"
      @slideshow="toggleSlideshow"
    />

    <p v-if="nextUnavailable" class="reader__toast" role="status">{{ tr("noNextGallery") }}</p>
  </section>
</template>

<style scoped>
.reader {
  position: fixed;
  inset: 0;
  z-index: 40;
  overflow: hidden;
  background: var(--gv-color-reader-surface);
  color: var(--gv-color-reader-on-surface);
  touch-action: none;
  user-select: none;
}

.reader--webtoon {
  touch-action: pan-y;
}

.reader__canvas {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.reader__stage {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  will-change: transform;
}

.reader__spread {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-1);
  width: 100%;
  height: 100%;
  padding: var(--gv-space-1);
  direction: ltr;
}

.reader__spread--rtl {
  flex-direction: row-reverse;
}

.reader__page {
  flex: 1 1 0;
  min-width: 0;
}

.reader__message {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-5);
  color: var(--gv-color-reader-on-surface);
  font: var(--gv-type-body-large);
  text-align: center;
}

.reader__retry {
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-5);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-reader-on-surface);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.reader__zones {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: 3fr 4fr 3fr;
  pointer-events: none;
}

.reader__zone {
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  pointer-events: none;
  cursor: pointer;
}

.reader__zone:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: -4px;
}

.reader__bar-layer {
  position: absolute;
  right: 0;
  left: 0;
  z-index: 4;
  transition:
    transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard),
    opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.reader__bar-layer--top {
  top: 0;
}

.reader__bar-layer--bottom {
  bottom: 0;
}

.reader__bar-layer--hidden {
  opacity: 0;
  pointer-events: none;
}

.reader__bar-layer--hidden.reader__bar-layer--top {
  transform: translateY(-100%);
}

.reader__bar-layer--hidden.reader__bar-layer--bottom {
  transform: translateY(100%);
}


.reader__toast {
  position: absolute;
  bottom: calc(var(--gv-size-reader-bar) + var(--gv-space-3));
  left: 50%;
  z-index: 5;
  margin: 0;
  padding: var(--gv-space-2) var(--gv-space-4);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-inverse-surface);
  color: var(--gv-color-inverse-on-surface);
  font: var(--gv-type-body-medium);
  transform: translateX(-50%);
}

@media (prefers-reduced-motion: reduce) {
  .reader__bar-layer {
    transition-duration: 1ms;
  }
}
</style>
