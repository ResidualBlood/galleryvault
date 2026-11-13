<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import { fetchOnlinePages, mapOnlineState, type OnlinePreviewItem, type OnlineState } from "@/api/eh";

const props = defineProps<{
  gid: number;
  token: string;
  total: number;
}>();

const emit = defineEmits<{ select: [page: number] }>();

const { t } = useI18n();

const items = ref<OnlinePreviewItem[]>([]);
const perPage = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const state = ref<OnlineState>("ok");
const sentinel = ref<HTMLElement | null>(null);

let controller: AbortController | null = null;
let observer: IntersectionObserver | null = null;
let lastLength = -1;

const totalPages = computed(() => Math.max(0, props.total));
const hasMore = computed(
  () => state.value === "ok" && !error.value && items.value.length < totalPages.value,
);
const loadedCount = computed(() => items.value.length);

function blockIndex(): number {
  if (!perPage.value) return 0;
  return Math.floor(items.value.length / perPage.value);
}

function mergeItems(incoming: OnlinePreviewItem[]): void {
  const seen = new Set(items.value.map((item) => item.index));
  const merged = [...items.value];
  for (const item of incoming) {
    if (seen.has(item.index)) continue;
    seen.add(item.index);
    merged.push(item);
  }
  merged.sort((a, b) => a.index - b.index);
  items.value = merged;
}

async function loadBlock(): Promise<void> {
  if (loading.value || !hasMore.value) return;
  const p = blockIndex();
  loading.value = true;
  error.value = null;
  controller?.abort();
  controller = new AbortController();
  try {
    const data = await fetchOnlinePages(props.gid, props.token, p, controller.signal);
    const mapped = mapOnlineState(data.state);
    state.value = mapped;
    if (mapped !== "ok") return;
    if (!perPage.value) perPage.value = data.per_page || data.items.length || 20;
    mergeItems(data.items);
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") return;
    error.value = caught instanceof Error ? caught.message : String(caught);
  } finally {
    loading.value = false;
  }
}

const sentinelInRange = (): boolean => {
  const element = sentinel.value;
  if (!element) return false;
  const rect = element.getBoundingClientRect();
  return rect.top < window.innerHeight + 600 && rect.bottom > -600;
};

function chainIfVisible(): void {
  if (loading.value || !hasMore.value || error.value) return;
  if (items.value.length === lastLength) return;
  lastLength = items.value.length;
  if (sentinelInRange()) void loadBlock();
}

watch(
  () => [items.value.length, loading.value, hasMore.value] as const,
  async () => {
    await nextTick();
    chainIfVisible();
  },
);

function onIntersect(entries: IntersectionObserverEntry[]): void {
  if (entries.some((entry) => entry.isIntersecting)) void loadBlock();
}

function retry(): void {
  error.value = null;
  void loadBlock();
}

function isSprite(item: OnlinePreviewItem): boolean {
  const thumb = item.thumb;
  return Boolean(thumb && thumb.url && thumb.w > 0 && thumb.h > 0);
}

function spriteViewBox(item: OnlinePreviewItem): string {
  const thumb = item.thumb;
  if (!thumb) return "0 0 1 1";
  return `${thumb.x} ${thumb.y} ${thumb.w} ${thumb.h}`;
}

onMounted(() => {
  void loadBlock();
  if (typeof IntersectionObserver === "function" && sentinel.value) {
    observer = new IntersectionObserver(onIntersect, { rootMargin: "600px" });
    observer.observe(sentinel.value);
  }
});

onBeforeUnmount(() => {
  controller?.abort();
  observer?.disconnect();
  observer = null;
});
</script>

<template>
  <div class="thumb-grid" data-testid="online-thumbs" :data-loaded="loadedCount">
    <button
      v-for="item in items"
      :key="item.index"
      type="button"
      class="thumb"
      :data-testid="isSprite(item) ? 'online-thumb' : 'online-thumb-placeholder'"
      :data-page="item.index + 1"
      :aria-label="t('online.detail.openPage', { page: item.index + 1 })"
      @click="emit('select', item.index)"
    >
      <svg
        v-if="isSprite(item) && item.thumb"
        class="thumb__sprite"
        :viewBox="spriteViewBox(item)"
        :aria-label="t('online.detail.thumbAlt', { page: item.index + 1 })"
        role="img"
      >
        <image :href="item.thumb.url" x="0" y="0" />
      </svg>
      <span v-else class="thumb__placeholder">
        <span class="thumb__number">{{ item.index + 1 }}</span>
        <span class="thumb__hint">{{ t("online.detail.pageOnly") }}</span>
      </span>
    </button>

    <template v-if="loading && items.length === 0">
      <Skeleton v-for="index in 10" :key="`skeleton-${index}`" variant="card" />
    </template>

    <div v-if="state !== 'ok'" class="thumb-grid__state" data-testid="online-thumbs-state">
      {{ t(`online.state.${state}.title`, t("online.state.error.title")) }}
    </div>

    <ErrorState
      v-else-if="error"
      class="thumb-grid__error"
      :title="t('online.detail.thumbsFailed')"
      :body="error"
      :retry-label="t('online.retry')"
      testid="online-thumbs-error"
      @retry="retry"
    />

    <div ref="sentinel" class="thumb-grid__sentinel" data-testid="online-thumbs-sentinel">
      <span v-if="loading && items.length > 0">{{ t("online.detail.thumbsLoading") }}</span>
      <span v-else-if="!hasMore && items.length > 0">{{ t("online.detail.thumbsEnd") }}</span>
    </div>
  </div>
</template>

<style scoped>
.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: var(--gv-space-2);
}

.thumb {
  display: block;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface-variant);
  cursor: pointer;
}

.thumb:hover {
  border-color: var(--gv-color-primary);
}

.thumb:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.thumb__sprite {
  display: block;
  width: 100%;
  height: 100%;
}

.thumb__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-1);
  width: 100%;
  height: 100%;
}

.thumb__number {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.thumb__hint {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.thumb-grid__state,
.thumb-grid__error {
  grid-column: 1 / -1;
}

.thumb-grid__state {
  padding: var(--gv-space-4);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-low);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.thumb-grid__sentinel {
  grid-column: 1 / -1;
  padding: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-align: center;
}
</style>
