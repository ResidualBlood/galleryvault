<script setup lang="ts">
/**
 * Recycle bin (PLAN polish §P5/P7, batch 23).
 *
 * The page keeps the two existing sources (`trash` / `expunged`) and the
 * restore / purge / redownload flows, but every row is now rendered by the
 * shared `GalleryCollection` + `GalleryCard` — the same component the library
 * uses — so the grid and list views, tag chips and selection control cannot
 * drift apart again. View mode is remembered per page (`recycle`) and falls
 * back to the list on narrow screens.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import IconButton from "@/components/ui/IconButton.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import type { GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
import type { GalleryItem } from "@/api/library";
import {
  fetchExpunged,
  fetchTrash,
  purgeGalleries,
  redownloadExpunged,
  restoreGalleries,
} from "@/api/recycle";
import { useViewMode } from "@/composables/useViewMode";
import { formatDate, PAGE_SIZES } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";
import { isTrashItem, recycleToGalleryItem, type RecycleItem } from "./items";

ensureMaintenanceMessages();

type Tab = "trash" | "expunged";
type Counts = { trash: number | null; expunged: number | null };

const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const { t } = useI18n();

const compactAtBoot =
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(max-width: 599px)").matches;
const view = useViewMode("recycle", {
  allowed: ["grid", "list"] as const,
  // 390 opens as a list; wider screens keep the library's grid default.
  fallback: compactAtBoot ? "list" : "grid",
});

const items = ref<RecycleItem[]>([]);
const total = ref(0);
const counts = ref<Counts>({ trash: null, expunged: null });
const loading = ref(true);
const error = ref("");
const selected = ref<number[]>([]);
const purgeOpen = ref(false);
const deleteFiles = ref(false);
const busyId = ref<number | null>(null);
const restoring = ref(false);
let seq = 0;

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

const tab = computed<Tab>(() => (first(route.query.tab) === "expunged" ? "expunged" : "trash"));
const page = computed(() => {
  const parsed = Number.parseInt(first(route.query.page), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
});
const pageSize = computed(() => {
  const parsed = Number.parseInt(first(route.query.page_size), 10);
  return Number.isFinite(parsed) && parsed >= 1 && parsed <= 500 ? parsed : settings.pageSize;
});
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const selectedCount = computed(() => selected.value.length);
const isTrash = computed(() => tab.value === "trash");

const tabOptions = computed(() => [
  {
    value: "trash",
    label:
      counts.value.trash === null
        ? t("maintenance.recycle.tabTrash")
        : t("maintenance.recycle.tabTrashCount", { n: counts.value.trash }),
  },
  {
    value: "expunged",
    label:
      counts.value.expunged === null
        ? t("maintenance.recycle.tabExpunged")
        : t("maintenance.recycle.tabExpungedCount", { n: counts.value.expunged }),
  },
]);

const galleryItems = computed<GalleryItem[]>(() =>
  items.value.map((item) =>
    recycleToGalleryItem(
      item,
      t(
        isTrashItem(item)
          ? "maintenance.recycle.tabTrashHint"
          : "maintenance.recycle.tabExpungedHint",
      ),
    ),
  ),
);

function badgesFor(item: GalleryItem): GalleryBadge[] {
  const date = formatDate(item.posted_at);
  const key = isTrash.value
    ? "maintenance.recycle.deletedAt"
    : "maintenance.recycle.expungedAt";
  return [
    {
      label: date || t("maintenance.recycle.noDate"),
      tone: isTrash.value ? "neutral" : "tertiary",
      title: t(key, { date: date || t("maintenance.recycle.noDate") }),
    },
  ];
}

function tabQuery(): Record<string, string> {
  return isTrash.value ? {} : { tab: tab.value };
}

function setTab(next: string): void {
  if (next !== "trash" && next !== "expunged") return;
  if (next === tab.value) return;
  void router.push({ name: "recycle", query: next === "trash" ? {} : { tab: next } });
}

function goPage(next: number): void {
  void router.push({
    name: "recycle",
    query: { ...tabQuery(), ...(next > 1 ? { page: String(next) } : {}) },
  });
}

function onPageSize(next: number): void {
  void router.push({
    name: "recycle",
    query: { ...tabQuery(), page_size: String(next) },
  });
}

function setSelected(id: number, next: boolean): void {
  selected.value = next
    ? [...new Set([...selected.value, id])]
    : selected.value.filter((value) => value !== id);
}

function clearSelection(): void {
  selected.value = [];
}

function goLibrary(): void {
  void router.push({ name: "library" });
}

async function loadCounts(): Promise<void> {
  const [trash, expunged] = await Promise.allSettled([
    fetchTrash(1, 1),
    fetchExpunged(1, 1),
  ]);
  if (trash.status === "fulfilled") counts.value.trash = trash.value.total ?? 0;
  if (expunged.status === "fulfilled") counts.value.expunged = expunged.value.total ?? 0;
}

async function load(): Promise<void> {
  const token = ++seq;
  loading.value = true;
  error.value = "";
  try {
    const data = isTrash.value
      ? await fetchTrash(page.value, pageSize.value)
      : await fetchExpunged(page.value, pageSize.value);
    if (token !== seq) return;
    items.value = data.items ?? [];
    total.value = data.total ?? 0;
    if (isTrash.value) counts.value.trash = data.total ?? 0;
    else counts.value.expunged = data.total ?? 0;
  } catch (cause) {
    if (token !== seq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (token === seq) loading.value = false;
  }
}

function requireSelection(): number[] | null {
  if (!selected.value.length) {
    ui.error(t("maintenance.recycle.selectRequired"));
    return null;
  }
  return selected.value;
}

async function restoreIds(ids: number[]): Promise<boolean> {
  try {
    const result = await restoreGalleries(ids);
    ui.success(t("maintenance.recycle.restored", { n: result.restored }));
    return true;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
    return false;
  }
}

async function restore(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  restoring.value = true;
  try {
    if (await restoreIds(ids)) {
      clearSelection();
      await load();
      await loadCounts();
    }
  } finally {
    restoring.value = false;
  }
}

async function restoreOne(id: number): Promise<void> {
  if (busyId.value !== null) return;
  busyId.value = id;
  try {
    if (await restoreIds([id])) {
      selected.value = selected.value.filter((value) => value !== id);
      await load();
      await loadCounts();
    }
  } finally {
    busyId.value = null;
  }
}

async function redownloadIds(ids: number[]): Promise<boolean> {
  try {
    const result = await redownloadExpunged(ids);
    const skipped = (result.skipped_no_gid ?? 0) + (result.skipped_no_token ?? 0);
    ui.success(
      t("maintenance.recycle.redownloadQueued", { n: result.queued }) +
        (skipped ? ` · ${t("maintenance.recycle.redownloadSkipped", { n: skipped })}` : ""),
    );
    return true;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
    return false;
  }
}

async function redownload(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  restoring.value = true;
  try {
    if (await redownloadIds(ids)) {
      clearSelection();
      await load();
      await loadCounts();
    }
  } finally {
    restoring.value = false;
  }
}

async function redownloadOne(id: number): Promise<void> {
  if (busyId.value !== null) return;
  busyId.value = id;
  try {
    if (await redownloadIds([id])) {
      selected.value = selected.value.filter((value) => value !== id);
      await load();
      await loadCounts();
    }
  } finally {
    busyId.value = null;
  }
}

async function purge(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    const result = await purgeGalleries(ids, deleteFiles.value);
    let message = t("maintenance.recycle.purged", { n: result.purged });
    if (result.failed_deletions?.length) {
      message += ` · ${t("maintenance.recycle.deleteFailed", { n: result.failed_deletions.length })}`;
    }
    ui.success(message);
    clearSelection();
    purgeOpen.value = false;
    deleteFiles.value = false;
    await load();
    await loadCounts();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

function openPurge(): void {
  if (!requireSelection()) return;
  deleteFiles.value = false;
  purgeOpen.value = true;
}

onMounted(() => {
  void loadCounts();
});

watch(
  () => [tab.value, page.value, pageSize.value] as const,
  () => {
    clearSelection();
    void load();
  },
  { immediate: true },
);
</script>

<template>
  <section class="recycle" data-testid="recycle-view">
    <PageHeader
      :title="t('maintenance.recycle.title')"
      :count="total"
      :count-label="t('maintenance.recycle.count', { n: total })"
      :subtitle="t('maintenance.recycle.subtitle')"
      testid="recycle-header"
    />

    <MaintenanceTabs active="recycle" />

    <Toolbar testid="recycle-toolbar">
      <ToolbarGroup>
        <SegmentedControl
          :model-value="tab"
          :options="tabOptions"
          :label="t('maintenance.recycle.sourceLabel')"
          testid="recycle-tabs"
          @change="setTab"
        />
      </ToolbarGroup>
      <ToolbarGroup end>
        <ViewModeToggle
          :model-value="view.mode.value"
          :options="view.available.value"
          testid="recycle-view-toggle"
          @update:model-value="view.setMode"
        />
      </ToolbarGroup>
    </Toolbar>

    <SelectionBar
      :count="selectedCount"
      :label="t('maintenance.shared.selected', { n: selectedCount })"
      :clear-label="t('maintenance.shared.clearSelection')"
      testid="recycle-selection"
      @clear="clearSelection"
    >
      <Button
        v-if="isTrash"
        data-testid="recycle-restore"
        :loading="restoring"
        @click="restore"
      >
        {{ t("maintenance.recycle.restore") }} ({{ selectedCount }})
      </Button>
      <Button
        v-else
        data-testid="recycle-redownload"
        :loading="restoring"
        @click="redownload"
      >
        {{ t("maintenance.recycle.redownload") }} ({{ selectedCount }})
      </Button>
      <template #danger>
        <Button
          variant="text"
          danger
          data-testid="recycle-purge"
          @click="openPurge"
        >
          {{ t("maintenance.recycle.purge") }} ({{ selectedCount }})
        </Button>
      </template>
    </SelectionBar>

    <div v-if="loading" class="recycle__skeletons" aria-hidden="true">
      <Skeleton
        v-for="index in 8"
        :key="index"
        :variant="view.mode.value === 'list' ? 'list' : 'card'"
      />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <GalleryCollection
      v-else-if="galleryItems.length"
      :items="galleryItems"
      :mode="view.mode.value"
      :selectable="true"
      :selected="selected"
      testid="recycle-grid"
      @select="setSelected"
    >
      <template #card="{ item }">
        <div class="recycle__cell" :data-testid="`recycle-item-${item.id}`">
          <GalleryCard
            :item="item"
            :variant="view.mode.value === 'list' ? 'list' : 'grid'"
            :badges="badgesFor(item)"
            selectable
            :selected="selected.includes(item.id)"
            tag-source="local"
            @select="setSelected"
          >
            <template #selection>
              <Checkbox
                :model-value="selected.includes(item.id)"
                :aria-label="t('maintenance.shared.select')"
                :data-testid="`recycle-select-${item.id}`"
                @update:model-value="(next) => setSelected(item.id, next)"
              />
            </template>
            <template #actions>
              <IconButton
                :name="isTrash ? 'retry' : 'downloads'"
                size="sm"
                :label="
                  isTrash
                    ? t('maintenance.recycle.restore')
                    : t('maintenance.recycle.redownload')
                "
                :disabled="busyId === item.id"
                :data-testid="`recycle-action-${item.id}`"
                @click.stop="isTrash ? restoreOne(item.id) : redownloadOne(item.id)"
              />
            </template>
          </GalleryCard>
        </div>
      </template>
    </GalleryCollection>

    <EmptyState
      v-else
      icon="recycle"
      :title="t('maintenance.recycle.empty')"
      :body="t('maintenance.recycle.emptyBody')"
      :action-label="t('maintenance.recycle.browseLibrary')"
      testid="recycle-empty"
      @action="goLibrary"
    />

    <Pager
      v-if="total > pageSize"
      :page="page"
      :total-pages="pages"
      :page-size="pageSize"
      :page-size-options="[...PAGE_SIZES]"
      testid="recycle-pager"
      @update:page="goPage"
      @update:page-size="onPageSize"
    />

    <ConfirmDialog
      :open="purgeOpen"
      :title="t('maintenance.recycle.purgeTitle')"
      :body="t('maintenance.recycle.purgeBody', { n: selectedCount })"
      :confirm-label="t('maintenance.recycle.purge')"
      danger
      testid="recycle-purge-dialog"
      @confirm="purge"
      @cancel="purgeOpen = false"
    >
      <Checkbox
        v-model="deleteFiles"
        :label="t('maintenance.recycle.deleteFiles')"
        data-testid="recycle-delete-files"
      />
    </ConfirmDialog>
  </section>
</template>

<style scoped>
.recycle {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

/* The virtual grid positions its direct children; the wrapper keeps the
   page-level row test hook while the shared card stays the visible surface. */
.recycle__cell {
  display: block;
  min-width: 0;
}

.recycle__cell :deep(.gallery-card) {
  height: 100%;
}

.recycle__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}
</style>
