<script setup lang="ts">
/**
 * Reading history.
 *
 * The page is a three-view collection (list by default, table and grid
 * available) built on the shared GalleryCollection. History rows carry no
 * tags: the list / table only show title, progress, last-read time, pages and
 * the continue-reading action (audit HS-05, PLAN §P5).
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import type { TableColumn } from "@/components/gallery/table-columns";
import { useViewMode } from "@/composables/useViewMode";
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
import type { GalleryItem } from "@/api/library";
import HistoryActions from "./HistoryActions.vue";
import HistoryRow from "./HistoryRow.vue";
import { ensureHistoryMessages } from "./messages";

ensureHistoryMessages();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();

const view = useViewMode("history", {
  allowed: ["grid", "list", "table"] as const,
  fallback: "list",
});

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
const pageSizeOptions = computed(() =>
  PAGE_SIZES.map((value) => ({ value: String(value), label: String(value) })),
);

const historyColumns: readonly TableColumn[] = [
  { key: "title", labelKey: "title", minWidth: 160, flex: 1, align: "start", priority: 100, pinned: true },
  { key: "progress", labelKey: "progress", width: 88, align: "end", priority: 60 },
  { key: "posted", labelKey: "readAt", width: 120, align: "end", hideBelow: 520, priority: 30 },
  { key: "pages", labelKey: "pages", width: 64, align: "end", priority: 50 },
  { key: "actions", labelKey: "actions", width: 112, align: "end", priority: 70 },
];

const entriesById = computed(() => new Map(items.value.map((entry) => [entry.gallery_id, entry])));

function first(value: unknown): string {
  if (Array.isArray(value)) return first(value[0]);
  return value === null || value === undefined ? "" : String(value);
}

function titleOf(entry: HistoryEntry): string {
  return entry.display_title || entry.title || entry.raw_title || `#${entry.gallery_id}`;
}

const mappedItems = computed<GalleryItem[]>(() =>
  items.value.map((entry) => {
    const totalPages = entry.total_pages ?? 0;
    const current = entry.current_page ?? 0;
    return {
      id: entry.gallery_id,
      gid: entry.gid,
      token: null,
      title: titleOf(entry),
      category: entry.category ?? "misc",
      page_count: totalPages,
      cover_url: null,
      tags: [],
      tag_count: 0,
      uploader: null,
      posted_at: entry.last_read_at,
      file_size: null,
      reading_progress: totalPages > 0 ? Math.min(current + 1, totalPages) : 0,
    };
  }),
);

function entryFor(item: GalleryItem): HistoryEntry {
  return entriesById.value.get(item.id) as HistoryEntry;
}

function readPageFor(item: GalleryItem): number {
  return entriesById.value.get(item.id)?.current_page ?? 0;
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

function goPage(target: number): void {
  void router.push({ name: "history", query: { page: String(target) } });
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

async function resetProgress(item: GalleryItem): Promise<void> {
  try {
    await clearGalleryProgress(item.id);
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
    <PageHeader
      :title="t('legacy.history')"
      :count="total"
      :count-label="t('history.page.loaded', { n: total })"
      :subtitle="t('history.page.subtitle')"
      testid="history-header"
    >
      <template #actions>
        <Button
          variant="text"
          danger
          icon="delete"
          data-testid="history-clear"
          @click="dialog = 'history'"
        >
          {{ t("legacy.clearHistory") }}
        </Button>
        <Button
          variant="text"
          danger
          icon="clear"
          data-testid="history-clear-progress"
          @click="dialog = 'progress'"
        >
          {{ t("legacy.clearProgress") }}
        </Button>
      </template>
    </PageHeader>

    <Toolbar testid="history-toolbar">
      <ToolbarGroup>
        <Select
          class="history__page-size"
          :model-value="String(pageSize)"
          :options="pageSizeOptions"
          :aria-label="t('legacy.perPage')"
          data-testid="history-page-size"
          @update:model-value="onPageSize"
        />
      </ToolbarGroup>
      <ToolbarGroup end>
        <ViewModeToggle
          :model-value="view.mode.value"
          :options="view.available.value"
          testid="history-view-toggle"
          @update:model-value="view.setMode"
        />
      </ToolbarGroup>
    </Toolbar>

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

    <GalleryCollection
      v-else
      :items="mappedItems"
      :mode="view.mode.value"
      :columns="historyColumns"
      testid="history-list"
    >
      <template #card="{ item }">
        <div v-if="view.mode.value === 'grid'" class="history-cell" :data-gallery-id="item.id">
          <GalleryCard :item="item" variant="grid" :show-meta="false">
            <template #actions>
              <HistoryActions :item="item" :read-page="readPageFor(item)" icon-only @reset="resetProgress(item)" />
            </template>
          </GalleryCard>
        </div>
        <li v-else class="history-row" :data-gallery-id="item.id">
          <HistoryRow
            :item="item"
            :entry="entryFor(item)"
            :read-page="readPageFor(item)"
            @reset="resetProgress(item)"
          />
        </li>
      </template>
      <template #actions="{ item }">
        <HistoryActions :item="item" :read-page="readPageFor(item)" icon-only @reset="resetProgress(item)" />
      </template>
    </GalleryCollection>

    <div v-if="items.length && pageCount > 1" class="history__footer">
      <Pager
        :page="page"
        :total-pages="pageCount"
        testid="history-pager"
        @update:page="goPage"
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
        <Button danger :loading="busy" data-testid="history-clear-confirm" @click="confirmClear">
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
        <Button danger :loading="busy" data-testid="history-clear-progress-confirm" @click="confirmClear">
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

.history__page-size {
  width: 96px;
}

.history__list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.history__footer {
  display: flex;
  justify-content: flex-end;
}

.history-cell {
  min-width: 0;
}

.history-row {
  display: block;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
