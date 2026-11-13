<script setup lang="ts">
/**
 * Missing-page integrity check (PLAN polish §P5/P7, batch 23).
 *
 * Rows go through the shared `GalleryCollection` / `GalleryCard`, so the grid
 * and list views match the library. The scan summary is independent of the
 * list (a clean scan must still be readable), `Scan` is the page's single
 * filled action, and bulk repair only exists in the selection bar.
 */
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import IconButton from "@/components/ui/IconButton.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
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
  fetchIntegrity,
  redownloadGallery,
  scanIntegrity,
  type IntegrityGallery,
  type IntegrityScanSummary,
} from "@/api/integrity";
import { useViewMode } from "@/composables/useViewMode";
import { formatDate, PAGE_SIZES } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";
import {
  integrityMismatchText,
  integrityToGalleryItem,
  missingPages,
} from "./items";

ensureMaintenanceMessages();

const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const { t } = useI18n();

const compactAtBoot =
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(max-width: 599px)").matches;
const view = useViewMode("integrity", {
  allowed: ["grid", "list"] as const,
  fallback: compactAtBoot ? "list" : "grid",
});

const items = ref<IntegrityGallery[]>([]);
const total = ref(0);
const summary = ref<IntegrityScanSummary | null>(null);
const loading = ref(true);
const error = ref("");
const selected = ref<number[]>([]);
const scanning = ref(false);
const repairing = ref(false);
const busyId = ref<number | null>(null);
const infoOpen = ref(false);
let seq = 0;

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

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
const itemCount = computed(() => items.value.length);

const galleryItems = computed<GalleryItem[]>(() =>
  items.value.map((item) =>
    integrityToGalleryItem(item, integrityMismatchText(item, t)),
  ),
);

const sourceById = computed(() => new Map(items.value.map((item) => [item.id, item])));

const summaryText = computed(() => {
  if (!summary.value) return "";
  const { scanned, total: scannedTotal, corrupt, completed_at } = summary.value;
  const finished = formatDate(completed_at);
  return finished
    ? t("maintenance.integrity.scanSummaryTime", {
        scanned,
        total: scannedTotal,
        corrupt,
        date: finished,
      })
    : t("maintenance.integrity.scanSummary", {
        scanned,
        total: scannedTotal,
        corrupt,
      });
});

const emptyBody = computed(() =>
  summary.value
    ? t("maintenance.integrity.emptyBodySummary", {
        scanned: summary.value.scanned,
        total: summary.value.total,
        corrupt: summary.value.corrupt,
      })
    : t("maintenance.integrity.emptyBody"),
);

function badgesFor(item: GalleryItem): GalleryBadge[] {
  const source = sourceById.value.get(item.id);
  const count = source ? missingPages(source) : 0;
  return [
    {
      label: t("maintenance.integrity.missingPages", { n: count }),
      tone: "error",
      title: source ? integrityMismatchText(source, t) : "",
    },
  ];
}

function setSelected(id: number, next: boolean): void {
  selected.value = next
    ? [...new Set([...selected.value, id])]
    : selected.value.filter((value) => value !== id);
}

function clearSelection(): void {
  selected.value = [];
}

function selectAll(): void {
  selected.value = items.value.map((item) => item.id);
}

function goPage(next: number): void {
  void router.push({
    name: "integrity",
    query: { ...(next > 1 ? { page: String(next) } : {}) },
  });
}

function onPageSize(next: number): void {
  void router.push({ name: "integrity", query: { page_size: String(next) } });
}

async function load(): Promise<void> {
  const token = ++seq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchIntegrity(page.value, pageSize.value);
    if (token !== seq) return;
    items.value = data.items ?? [];
    total.value = data.total ?? 0;
    summary.value = data.magic_scan ?? null;
  } catch (cause) {
    if (token !== seq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (token === seq) loading.value = false;
  }
}

async function scan(): Promise<void> {
  if (scanning.value) return;
  scanning.value = true;
  try {
    const result = await scanIntegrity();
    if (result.status === "paused") {
      ui.info(
        result.detail ||
          `${t("maintenance.integrity.paused")} — ${t("maintenance.integrity.pauseHint")}`,
      );
    } else {
      summary.value = result;
      ui.success(t("maintenance.integrity.scanStarted"));
      await load();
    }
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    scanning.value = false;
  }
}

async function repair(): Promise<void> {
  if (!selected.value.length) {
    ui.error(t("maintenance.integrity.selectRequired"));
    return;
  }
  repairing.value = true;
  const ids = [...selected.value];
  try {
    const results = await Promise.allSettled(ids.map((id) => redownloadGallery(id)));
    const ok = results.filter((result) => result.status === "fulfilled").length;
    const failed = results.length - ok;
    ui.success(
      t("maintenance.integrity.repairQueued", { ok }) +
        (failed ? ` · ${t("maintenance.integrity.repairFailed", { failed })}` : ""),
    );
    clearSelection();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    repairing.value = false;
  }
}

async function repairOne(id: number): Promise<void> {
  if (busyId.value !== null) return;
  busyId.value = id;
  try {
    await redownloadGallery(id);
    ui.success(t("maintenance.integrity.repairQueued", { ok: 1 }));
    selected.value = selected.value.filter((value) => value !== id);
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    busyId.value = null;
  }
}

watch(
  () => [page.value, pageSize.value] as const,
  () => {
    clearSelection();
    void load();
  },
  { immediate: true },
);
</script>

<template>
  <section class="integrity" data-testid="integrity-view">
    <PageHeader
      :title="t('maintenance.integrity.title')"
      :count="total"
      :count-label="t('maintenance.integrity.count', { n: total })"
      :subtitle="t('maintenance.integrity.subtitle')"
      testid="integrity-header"
    />

    <p v-if="summary && itemCount" class="integrity__summary" data-testid="integrity-summary">
      {{ summaryText }}
    </p>

    <MaintenanceTabs active="integrity" />

    <Toolbar testid="integrity-toolbar">
      <ToolbarGroup>
        <Button
          icon="search"
          data-testid="integrity-scan"
          :loading="scanning"
          @click="scan"
        >
          {{ t("maintenance.integrity.scan") }}
        </Button>
        <Button
          variant="outlined"
          data-testid="integrity-select-all"
          :disabled="!itemCount"
          @click="selectAll"
        >
          {{ t("maintenance.integrity.selectAll") }}
        </Button>
      </ToolbarGroup>
      <ToolbarGroup end>
        <ViewModeToggle
          :model-value="view.mode.value"
          :options="view.available.value"
          testid="integrity-view-toggle"
          @update:model-value="view.setMode"
        />
      </ToolbarGroup>
    </Toolbar>

    <div class="integrity__info">
      <Button
        variant="text"
        :icon="infoOpen ? 'chevron-up' : 'chevron-down'"
        :aria-expanded="infoOpen"
        data-testid="integrity-info-toggle"
        @click="infoOpen = !infoOpen"
      >
        {{ t("maintenance.integrity.infoSummary") }}
      </Button>
      <p v-if="infoOpen" class="integrity__info-body" data-testid="integrity-info">
        {{ t("maintenance.integrity.infoDetail") }}
      </p>
    </div>

    <SelectionBar
      :count="selectedCount"
      :label="t('maintenance.shared.selected', { n: selectedCount })"
      :clear-label="t('maintenance.shared.clearSelection')"
      testid="integrity-selection"
      @clear="clearSelection"
    >
      <Button
        data-testid="integrity-repair"
        :loading="repairing"
        @click="repair"
      >
        {{ t("maintenance.integrity.repair") }} ({{ selectedCount }})
      </Button>
    </SelectionBar>

    <div v-if="loading" class="integrity__skeletons" aria-hidden="true">
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
      testid="integrity-grid"
      @select="setSelected"
    >
      <template #card="{ item }">
        <div class="integrity__cell" :data-testid="`integrity-item-${item.id}`">
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
                :data-testid="`integrity-select-${item.id}`"
                @update:model-value="(next) => setSelected(item.id, next)"
              />
            </template>
            <template #actions>
              <IconButton
                name="retry"
                size="sm"
                :label="t('maintenance.integrity.repair')"
                :disabled="busyId === item.id"
                :data-testid="`integrity-action-${item.id}`"
                @click.stop="repairOne(item.id)"
              />
            </template>
          </GalleryCard>
        </div>
      </template>
    </GalleryCollection>

    <EmptyState
      v-else
      icon="integrity"
      :title="t('maintenance.integrity.empty')"
      :body="emptyBody"
      :action-label="t('maintenance.integrity.scanNow')"
      testid="integrity-empty"
      @action="scan"
    />

    <Pager
      v-if="total > pageSize"
      :page="page"
      :total-pages="pages"
      :page-size="pageSize"
      :page-size-options="[...PAGE_SIZES]"
      testid="integrity-pager"
      @update:page="goPage"
      @update:page-size="onPageSize"
    />
  </section>
</template>

<style scoped>
.integrity {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.integrity__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.integrity__info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--gv-space-2);
  padding: var(--gv-space-2) var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.integrity__info-body {
  margin: 0 var(--gv-space-3);
}

/* The virtual grid positions its direct children; the wrapper keeps the
   page-level row test hook while the shared card stays the visible surface. */
.integrity__cell {
  display: block;
  min-width: 0;
}

.integrity__cell :deep(.gallery-card) {
  height: 100%;
}

.integrity__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}
</style>
