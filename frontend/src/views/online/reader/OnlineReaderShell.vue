<script setup lang="ts">
/**
 * Online reader body (`online-direct` main path, `online-proxy` per device).
 *
 * ReaderShell owns modes, gestures and the paginated/webtoon rendering; this
 * component only supplies the PageSource, online progress, the persistent
 * action strip, the quota notice and the blocked-page fallbacks. It is router
 * agnostic so the E2E harness can mount it without the route table.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import ReaderShell from "@/views/reader/ReaderShell.vue";
import Button from "@/components/ui/Button.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Icon from "@/components/icons/Icon.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import GalleryActions from "@/components/actions/GalleryActions.vue";
import OnlineStateNotice from "@/views/online/list/OnlineStateNotice.vue";
import { ensureOnlineMessages } from "@/views/online/list/messages";
import {
  fetchOnlineDetail,
  mapOnlineState,
  officialGalleryUrl,
  type OnlineGallery,
  type OnlineState,
} from "@/api/eh";
import {
  fetchOnlineProgress,
  fetchOnlineQuota,
  saveOnlineProgress,
  type OnlineQuota,
} from "@/api/eh-reader";
import type { PageProgress, PageSource } from "@/reader/source";
import {
  OnlineDirectPageSource,
  createOnlinePageSource,
  readOnlineImageMode,
  writeOnlineImageMode,
  type OnlineImageMode,
  type OnlineSourceEvent,
} from "@/reader/sources";
import { useOnlineReaderI18n } from "./i18n";

ensureOnlineMessages();

const props = withDefaults(
  defineProps<{
    gid: number;
    token: string;
    /** Explicit start page (0-based). Null/undefined resumes stored progress. */
    initialPage?: number | null;
  }>(),
  { initialPage: null },
);

const emit = defineEmits<{
  close: [];
  pageChange: [page: number];
}>();

const { tr } = useOnlineReaderI18n();

const gallery = ref<OnlineGallery | null>(null);
const state = ref<OnlineState>("ok");
const loading = ref(true);
const loadError = ref(false);
const ready = ref(false);
const total = ref(0);

const mode = ref<OnlineImageMode>(readOnlineImageMode());
const reloadKey = ref(0);
const currentPage = ref(0);
const mountPage = ref(0);

const quota = ref<OnlineQuota | null>(null);
const quotaNotice = ref(false);
const failure = ref<"image_failed" | "placeholder" | null>(null);
const failurePage = ref<number | null>(null);

const source = computed<PageSource>(() => {
  // `reloadKey` is a dependency so switching mode/retrying rebuilds the source
  // and drops every cached (possibly dead) URL.
  void reloadKey.value;
  return createOnlinePageSource({
    mode: mode.value,
    gid: props.gid,
    token: props.token,
    pageCount: total.value,
  });
});

const officialUrl = computed(() => {
  if (props.gid > 0 && props.token) return officialGalleryUrl(props.gid, props.token);
  return "";
});

const atEnd = computed(
  () => total.value > 0 && currentPage.value >= total.value - 1,
);

const showStateNotice = computed(
  () => !loading.value && !loadError.value && state.value !== "ok",
);

const showEmpty = computed(
  () => !loading.value && !loadError.value && state.value === "ok" && total.value === 0,
);

const quotaUsage = computed(() => {
  const limit = quota.value?.image_limit;
  return limit ? tr("quota.usage", { current: limit.current, limit: limit.limit }) : "";
});

const modeHint = computed(() =>
  tr(mode.value === "direct" ? "imageMode.directHint" : "imageMode.proxyHint"),
);

const modeOptions = computed(() => [
  { value: "direct", label: tr("imageMode.direct") },
  { value: "proxy", label: tr("imageMode.proxy") },
]);

function onModeChange(value: string): void {
  setMode(value === "proxy" ? "proxy" : "direct");
}

/* ------------------------------------------------------------------ loading */

async function readStoredProgress() {
  if (typeof props.initialPage === "number") return null;
  try {
    return await fetchOnlineProgress(props.gid, props.token);
  } catch {
    return null;
  }
}

function clampPage(page: number): number {
  if (total.value <= 0) return 0;
  return Math.min(Math.max(0, Math.floor(page)), total.value - 1);
}

async function boot(): Promise<void> {
  loading.value = true;
  loadError.value = false;
  ready.value = false;
  failure.value = null;
  quotaNotice.value = false;
  quota.value = null;
  try {
    const [detail, stored] = await Promise.all([
      fetchOnlineDetail(props.gid, props.token),
      readStoredProgress(),
    ]);
    const mapped = mapOnlineState(detail.state);
    if (mapped !== "ok" || !detail.gallery) {
      state.value = mapped === "ok" ? "error" : mapped;
      gallery.value = null;
      total.value = 0;
      return;
    }
    state.value = "ok";
    gallery.value = detail.gallery;
    total.value = Math.max(0, Number(detail.gallery.pages) || 0);
    currentPage.value =
      typeof props.initialPage === "number"
        ? clampPage(props.initialPage)
        : stored
          ? clampPage(stored.page - 1)
          : 0;
    mountPage.value = currentPage.value;

    ready.value = total.value > 0;
  } catch {
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

/* -------------------------------------------------------------------- events */

function handleSourceEvent(event: OnlineSourceEvent): void {
  if (event.type === "quota") {
    quotaNotice.value = true;
    failure.value = null;
    void loadQuota();
    return;
  }
  failure.value = event.reason;
  failurePage.value = event.page;
}

function subscribe(current: PageSource): () => void {
  if (current instanceof OnlineDirectPageSource) {
    return current.subscribe(handleSourceEvent);
  }
  return () => {};
}

watch(
  source,
  (current, previous, onCleanup) => {
    const off = subscribe(current);
    onCleanup(() => {
      off();
      if (previous instanceof OnlineDirectPageSource) previous.dispose();
    });
  },
  { immediate: true },
);

async function loadQuota(): Promise<void> {
  try {
    quota.value = await fetchOnlineQuota();
  } catch {
    quota.value = null;
  }
}

/* ---------------------------------------------------------------- navigation */

/**
 * ReaderShell owns the progress writer; this sender is the only sink for
 * online reading. It never touches `/api/galleries/{id}/progress`.
 */
function sendProgress(payload: PageProgress): Promise<unknown> {
  return saveOnlineProgress(props.gid, props.token, {
    page: payload.current_page + 1,
    total_pages: payload.total_pages,
    title: gallery.value?.title ?? null,
    thumb: gallery.value?.thumb ?? null,
  }).then(() => undefined);
}

function onPageChange(page: number): void {
  currentPage.value = page;
  emit("pageChange", page);

  const current = source.value;
  // ReaderShell caches a resolved URL per page. When that URL is past
  // `expires_at`, remounting is the only way to force a fresh resolve without
  // touching the shell; it resumes on the same page.
  if (
    current instanceof OnlineDirectPageSource &&
    !current.isThrottled &&
    current.isExpired(page)
  ) {
    mountPage.value = page;
    reloadKey.value += 1;
  }
}

function retryPage(): void {
  failure.value = null;
  failurePage.value = null;
  mountPage.value = currentPage.value;
  reloadKey.value += 1;
}

function setMode(next: OnlineImageMode): void {
  if (next === mode.value) return;
  mode.value = writeOnlineImageMode(next);
  failure.value = null;
  failurePage.value = null;
  quotaNotice.value = false;
  mountPage.value = currentPage.value;
  reloadKey.value += 1;
}

onBeforeUnmount(() => {
  if (source.value instanceof OnlineDirectPageSource) source.value.dispose();
});

void boot();
</script>

<template>
  <section
    class="online-reader"
    data-testid="online-reader"
    :data-mode="mode"
    :data-page="currentPage"
    :data-total="total"
  >
    <div v-if="loading" class="online-reader__state" data-testid="online-reader-loading">
      <span class="online-reader__spinner" aria-hidden="true" />
      <p class="online-reader__state-text">{{ tr("loading") }}</p>
    </div>

    <div v-else-if="loadError" class="online-reader__state" data-testid="online-reader-error">
      <ErrorState
        :title="tr('loadFailed')"
        :retry-label="tr('retry')"
        testid="online-reader-error-state"
        @retry="boot"
      />
    </div>

    <OnlineStateNotice
      v-else-if="showStateNotice"
      :state="state"
      @retry="boot"
    />

    <p v-else-if="showEmpty" class="online-reader__state" data-testid="online-reader-empty">
      {{ tr("empty") }}
    </p>

    <template v-else-if="ready">
      <ReaderShell
        :key="`${mode}-${reloadKey}`"
        :gallery-id="props.gid"
        :page-count="total"
        :initial-page="mountPage"
        :title="gallery?.title ?? ''"
        :source="source"
        :progress-sender="sendProgress"
        @close="emit('close')"
        @page-change="onPageChange"
      >
        <template #bar-actions>
          <div class="online-reader__actions" data-testid="online-reader-actions" data-no-gesture>
            <div
              class="online-reader__mode"
              data-testid="online-reader-mode"
              :data-mode="mode"
              :title="modeHint"
            >
              <SegmentedControl
                testid="online-reader-mode-control"
                :model-value="mode"
                :options="modeOptions"
                :label="tr('imageMode.label')"
                @change="onModeChange"
              />
            </div>
            <GalleryActions
              :gid="props.gid"
              :token="props.token"
              :title="gallery?.title ?? ''"
              source="online"
              density="toolbar"
              :show-read="false"
              :favorited="gallery?.favorited ?? false"
              :favcat="gallery?.favcat ?? null"
              :in-library="gallery?.in_library ?? false"
              :download-status="gallery?.download?.status ?? null"
              :download-current-page="gallery?.download?.current_page ?? 0"
              :download-total-pages="gallery?.download?.total_pages ?? null"
            />
          </div>
        </template>
      </ReaderShell>

      <div
        v-if="quotaNotice"
        class="online-reader__quota"
        data-testid="online-reader-quota"
        role="status"
        data-no-gesture
      >
        <div class="online-reader__quota-text">
          <strong class="online-reader__quota-title">
            <Icon name="status-warning" size="dense" />
            {{ tr("quota.title") }}
          </strong>
          <span>{{ tr("quota.body") }}</span>
          <span v-if="quotaUsage" class="online-reader__quota-usage" data-testid="online-reader-quota-usage">
            {{ quotaUsage }}
          </span>
          <span v-else class="online-reader__quota-usage">{{ tr("quota.usageUnknown") }}</span>
        </div>
        <div class="online-reader__quota-actions">
          <Button
            variant="filled"
            icon="status-challenge"
            data-testid="online-reader-quota-proxy"
            @click="setMode('proxy')"
          >
            {{ tr("quota.proxy") }}
          </Button>
          <a
            v-if="officialUrl"
            class="online-reader__link"
            data-testid="online-reader-quota-official"
            :href="officialUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Icon name="external-link" size="dense" />
            {{ tr("quota.official") }}
          </a>
          <Button
            variant="text"
            data-testid="online-reader-quota-close"
            @click="quotaNotice = false"
          >
            {{ tr("quota.close") }}
          </Button>
        </div>
      </div>

      <div
        v-if="failure"
        class="online-reader__panel"
        data-testid="online-reader-blocked"
        role="alertdialog"
        :data-reason="failure"
        :data-page="failurePage ?? undefined"
        data-no-gesture
      >
        <h2 class="online-reader__panel-title">
          <Icon name="status-blocked" size="dense" />
          {{ tr("blocked.title") }}
        </h2>
        <p class="online-reader__panel-body">{{ tr("blocked.body") }}</p>
        <div class="online-reader__panel-actions">
          <Button
            variant="filled"
            icon="status-challenge"
            data-testid="online-reader-use-proxy"
            @click="setMode('proxy')"
          >
            {{ tr("blocked.proxy") }}
          </Button>
          <a
            v-if="officialUrl"
            class="online-reader__link"
            data-testid="online-reader-official"
            :href="officialUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Icon name="external-link" size="dense" />
            {{ tr("blocked.official") }}
          </a>
          <Button
            variant="text"
            icon="retry"
            data-testid="online-reader-retry-page"
            @click="retryPage"
          >
            {{ tr("blocked.retry") }}
          </Button>
        </div>
      </div>

      <div
        v-if="atEnd && !failure && !quotaNotice"
        class="online-reader__end"
        data-testid="online-reader-end"
        data-no-gesture
      >
        <p class="online-reader__end-title">{{ tr("end.title") }}</p>
        <div class="online-reader__end-actions">
          <GalleryActions
            :gid="props.gid"
            :token="props.token"
            :title="gallery?.title ?? ''"
            source="online"
            density="detail"
            :show-read="false"
            :favorited="gallery?.favorited ?? false"
            :favcat="gallery?.favcat ?? null"
            :in-library="gallery?.in_library ?? false"
            :download-status="gallery?.download?.status ?? null"
            :download-current-page="gallery?.download?.current_page ?? 0"
            :download-total-pages="gallery?.download?.total_pages ?? null"
          />
          <Button
            variant="outlined"
            icon="back"
            data-testid="online-reader-back"
            @click="emit('close')"
          >
            {{ tr("end.back") }}
          </Button>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.online-reader {
  position: relative;
  min-height: 100vh;
  background: var(--gv-color-reader-surface);
  color: var(--gv-color-reader-on-surface);
}

.online-reader__state {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  margin: 0;
  padding: var(--gv-space-5);
  background: var(--gv-color-reader-surface);
  color: var(--gv-color-reader-on-surface);
  font: var(--gv-type-body-large);
  text-align: center;
}

/* Rendered through ReaderShell's bottom-bar slot, so the strip appears and
   hides with the bars instead of floating over the page forever (OR-05). */
.online-reader__actions {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  padding: var(--gv-space-1);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 94%, transparent);
  box-shadow: var(--gv-elev-3);
}

.online-reader__mode {
  display: flex;
  align-items: center;
}

/* The shared segmented control sits on the chip step (32); this strip is a
   control-lg row, so lift the segments to the same step. */
.online-reader__mode :deep(.segmented__item) {
  height: var(--gv-size-control-lg);
}

.online-reader__mode :deep(.segmented__label) {
  white-space: nowrap;
}

.online-reader__quota {
  position: fixed;
  top: calc(var(--gv-size-reader-bar) + var(--gv-space-2));
  left: 50%;
  z-index: 61;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  width: min(560px, calc(100vw - 2 * var(--gv-space-4)));
  padding: var(--gv-space-3) var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 96%, transparent);
  box-shadow: var(--gv-elev-3);
  color: var(--gv-color-on-surface);
  transform: translateX(-50%);
}

.online-reader__quota-text {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.online-reader__quota-title {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  font: var(--gv-type-title-small);
  color: var(--gv-color-error);
}

.online-reader__quota-usage {
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface);
}

.online-reader__quota-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.online-reader__panel {
  position: fixed;
  top: 50%;
  left: 50%;
  z-index: 62;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  width: min(480px, calc(100vw - 2 * var(--gv-space-5)));
  padding: var(--gv-space-5);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-6);
  color: var(--gv-color-on-surface);
  transform: translate(-50%, -50%);
  text-align: center;
}

.online-reader__panel-title {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-error);
}

.online-reader__panel-body {
  margin: 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.online-reader__panel-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-2);
}

.online-reader__end {
  position: fixed;
  right: var(--gv-space-4);
  bottom: calc(var(--gv-size-reader-bar) + var(--gv-space-4));
  left: var(--gv-space-4);
  z-index: 60;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  max-width: 560px;
  margin: 0 auto;
  padding: var(--gv-space-3) var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 96%, transparent);
  box-shadow: var(--gv-elev-3);
  color: var(--gv-color-on-surface);
}

.online-reader__end-title {
  margin: 0;
  font: var(--gv-type-title-small);
}

.online-reader__end-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.online-reader__link {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-control-lg);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.online-reader__link:hover {
  background: color-mix(in srgb, var(--gv-color-primary) 12%, transparent);
}

.online-reader__link:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: 2px;
}

@media (max-width: 599px) {
  .online-reader__end {
    right: var(--gv-space-2);
    left: var(--gv-space-2);
  }
}
</style>
