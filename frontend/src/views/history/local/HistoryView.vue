<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import { PAGE_SIZES, clampPageSize } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
import {
  clearAllProgress,
  clearGalleryProgress,
  clearHistory,
  fetchHistory,
  type HistoryEntry,
} from "@/api/history";
import { ensureHistoryMessages } from "./messages";

ensureHistoryMessages();

const { t, locale } = useI18n();
const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();

const items = ref<HistoryEntry[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(true);
const error = ref("");
const dialog = ref<"" | "history" | "progress">("");
const busy = ref(false);
let requestSeq = 0;

const pageSize = computed(() => clampPageSize(settings.pageSize, 24));
const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / Math.max(1, pageSize.value))),
);
const pageLinks = computed(() => {
  const start = Math.max(1, page.value - 2);
  const end = Math.min(pageCount.value, page.value + 2);
  const pages: number[] = [];
  for (let value = start; value <= end; value += 1) pages.push(value);
  return pages;
});
const pageSizeOptions = computed(() =>
  PAGE_SIZES.map((value) => ({ value: String(value), label: String(value) })),
);

function first(value: unknown): string {
  if (Array.isArray(value)) return first(value[0]);
  return value === null || value === undefined ? "" : String(value);
}

function titleOf(entry: HistoryEntry): string {
  return entry.display_title || entry.title || entry.raw_title || `#${entry.gallery_id}`;
}

function progressText(entry: HistoryEntry): string {
  const totalPages = entry.total_pages ?? 0;
  return t("history.page.progressLine", {
    current: Math.min((entry.current_page ?? 0) + 1, Math.max(1, totalPages)),
    total: totalPages || "?",
  });
}

function formatDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat(locale.value === "zh" ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function syncFromRoute(): void {
  const parsed = Number.parseInt(first(route.query.page), 10);
  page.value = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  void load();
}

async function load(): Promise<void> {
  const seq = ++requestSeq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchHistory(page.value, pageSize.value);
    if (seq !== requestSeq) return;
    items.value = data.items;
    total.value = data.total;
  } catch (cause) {
    if (seq !== requestSeq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
    items.value = [];
    total.value = 0;
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

function onPageSize(value: string): void {
  const next = clampPageSize(value, settings.pageSize);
  settings.setPageSize(next);
  void router.push({ name: "history", query: { page: "1" } });
}

async function confirmClear(): Promise<void> {
  if (busy.value) return;
  const kind = dialog.value;
  busy.value = true;
  try {
    if (kind === "history") {
      await clearHistory();
      ui.success(t("legacy.historyCleared"));
    } else {
      await clearAllProgress();
      ui.success(t("legacy.progressCleared"));
    }
    dialog.value = "";
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
  } finally {
    busy.value = false;
  }
}

async function resetProgress(entry: HistoryEntry): Promise<void> {
  try {
    await clearGalleryProgress(entry.gallery_id);
    ui.success(t("legacy.progressClearedSingle"));
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
  }
}

watch(
  () => route.query,
  () => syncFromRoute(),
  { immediate: true, deep: true },
);

onBeforeUnmount(() => {
  requestSeq += 1;
});
</script>

<template>
  <section class="history" data-testid="history-view">
    <header class="history__header">
      <p class="history__eyebrow">{{ t("history.page.eyebrow") }}</p>
      <div class="history__heading">
        <h1 class="history__title">{{ t("legacy.history") }}</h1>
        <span class="history__total">{{ t("history.page.loaded", { n: total }) }}</span>
      </div>
      <div class="history__actions">
        <Button
          variant="outlined"
          size="compact"
          data-testid="history-clear"
          @click="dialog = 'history'"
        >
          {{ t("legacy.clearHistory") }}
        </Button>
        <Button
          variant="outlined"
          size="compact"
          data-testid="history-clear-progress"
          @click="dialog = 'progress'"
        >
          {{ t("legacy.clearProgress") }}
        </Button>
      </div>
    </header>

    <ErrorState
      v-if="error && !items.length"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('common.retry')"
      @retry="load"
    />

    <div v-else-if="loading" class="history__list" aria-hidden="true">
      <Skeleton v-for="index in 4" :key="index" variant="list" />
    </div>

    <EmptyState
      v-else-if="!items.length"
      :title="t('legacy.noHistory')"
      :body="t('legacy.noHistory')"
      testid="history-empty"
    />

    <ul v-else class="history__list" data-testid="history-list">
      <li
        v-for="entry in items"
        :key="entry.gallery_id"
        class="history-row"
        :data-gallery-id="entry.gallery_id"
      >
        <div class="history-row__main">
          <RouterLink class="history-row__title" :to="`/gallery/${entry.gallery_id}`">
            {{ titleOf(entry) }}
          </RouterLink>
          <p class="history-row__meta">
            <span>{{ progressText(entry) }}</span>
            <span v-if="entry.last_read_at">
              · {{ t("history.page.readAt") }} {{ formatDate(entry.last_read_at) }}
            </span>
          </p>
        </div>
        <div class="history-row__actions">
          <RouterLink
            class="history-row__read"
            :to="`/reader/${entry.gallery_id}/${entry.current_page ?? 0}`"
          >
            {{ t("legacy.readNow") }}
          </RouterLink>
          <Button
            variant="text"
            size="compact"
            data-testid="history-reset-row"
            :title="t('legacy.markUnread')"
            @click="resetProgress(entry)"
          >
            {{ t("history.page.clearSingle") }}
          </Button>
        </div>
      </li>
    </ul>

    <div v-if="items.length" class="history__footer">
      <nav class="history__pager" :aria-label="t('legacy.pageNav')">
        <RouterLink
          v-if="page > 1"
          class="history__page"
          :to="{ name: 'history', query: { page: page - 1 } }"
        >
          ‹
        </RouterLink>
        <RouterLink
          v-for="value in pageLinks"
          :key="value"
          class="history__page"
          :class="{ 'history__page--current': value === page }"
          :aria-current="value === page ? 'page' : undefined"
          :to="{ name: 'history', query: { page: value } }"
        >
          {{ value }}
        </RouterLink>
        <RouterLink
          v-if="page < pageCount"
          class="history__page"
          :to="{ name: 'history', query: { page: page + 1 } }"
        >
          ›
        </RouterLink>
      </nav>
      <Select
        class="history__page-size"
        :model-value="String(pageSize)"
        :options="pageSizeOptions"
        :label="t('legacy.perPage')"
        data-testid="history-page-size"
        @update:model-value="onPageSize"
      />
    </div>

    <Dialog
      :open="dialog === 'history'"
      :title="t('legacy.clearHistory')"
      testid="history-clear-dialog"
      @close="dialog = ''"
    >
      <p>{{ t("legacy.confirmClearHistory") }}</p>
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button :loading="busy" data-testid="history-clear-confirm" @click="confirmClear">
          {{ t("legacy.clearHistory") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="dialog === 'progress'"
      :title="t('legacy.clearProgress')"
      testid="history-clear-progress-dialog"
      @close="dialog = ''"
    >
      <p>{{ t("legacy.confirmClearProgress") }}</p>
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button :loading="busy" data-testid="history-clear-progress-confirm" @click="confirmClear">
          {{ t("legacy.clearProgress") }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.history__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.history__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.history__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--gv-space-3);
}

.history__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.history__total {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.history__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.history__list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
  min-height: 72px;
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.history-row__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.history-row__title {
  overflow: hidden;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-row__title:hover {
  text-decoration: underline;
}

.history-row__meta {
  display: flex;
  flex-wrap: wrap;
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.history-row__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--gv-space-1);
}

.history-row__read {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.history-row__read:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.history__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3) 0;
}

.history__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.history__page {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.history__page:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.history__page--current {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.history__page-size {
  min-width: 120px;
}

@media (max-width: 599px) {
  .history-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .history-row__actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
