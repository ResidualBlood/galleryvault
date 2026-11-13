<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import {
  fetchExpunged,
  fetchTrash,
  purgeGalleries,
  redownloadExpunged,
  restoreGalleries,
  type ExpungedGallery,
  type TrashGallery,
} from "@/api/recycle";
import { useUiStore } from "@/stores/ui";
import { useSettingsStore } from "@/stores/settings";
import { formatDate } from "@/stores/library";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
import PagerBar from "@/views/updates/components/PagerBar.vue";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

type Tab = "trash" | "expunged";
type RecycleItem = TrashGallery | ExpungedGallery;

const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const { t } = useI18n();

const items = ref<RecycleItem[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
const selected = ref<number[]>([]);
const purgeOpen = ref(false);
const deleteFiles = ref(false);
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

function itemDate(item: RecycleItem): string {
  return formatDate(
    "trashed_at" in item ? item.trashed_at : ("updated_at" in item ? item.updated_at : null),
  );
}

function itemTitle(item: RecycleItem): string {
  return item.title || `#${item.id}`;
}

function setTab(next: Tab): void {
  void router.push({
    name: "recycle",
    query: next === "trash" ? {} : { tab: next },
  });
}

function goPage(next: number): void {
  void router.push({
    name: "recycle",
    query: { ...(tab.value === "trash" ? {} : { tab: tab.value }), page: next },
  });
}

function toggle(id: number): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id];
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

async function restore(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    const result = await restoreGalleries(ids);
    ui.success(t("maintenance.recycle.restored", { n: result.restored }));
    selected.value = [];
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function redownload(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    const result = await redownloadExpunged(ids);
    const skipped = (result.skipped_no_gid ?? 0) + (result.skipped_no_token ?? 0);
    ui.success(
      t("maintenance.recycle.redownloadQueued", { n: result.queued }) +
        (skipped ? ` · ${t("maintenance.recycle.redownloadSkipped", { n: skipped })}` : ""),
    );
    selected.value = [];
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
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
    selected.value = [];
    purgeOpen.value = false;
    deleteFiles.value = false;
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

function openPurge(): void {
  if (!requireSelection()) return;
  deleteFiles.value = false;
  purgeOpen.value = true;
}

watch(
  () => [tab.value, page.value, pageSize.value] as const,
  () => {
    selected.value = [];
    void load();
  },
  { immediate: true },
);
</script>

<template>
  <section class="recycle" data-testid="recycle-view">
    <header class="recycle__header">
      <p class="recycle__eyebrow">{{ t("maintenance.recycle.eyebrow") }}</p>
      <h1 class="recycle__title">{{ t("maintenance.recycle.title") }}</h1>
      <p class="recycle__subtitle">{{ t("maintenance.recycle.subtitle") }}</p>
    </header>

    <MaintenanceTabs active="recycle" />

    <div class="recycle__tabs" role="tablist" aria-label="recycle">
      <Button
        :variant="isTrash ? 'tonal' : 'outlined'"
        size="compact"
        data-testid="recycle-tab-trash"
        @click="setTab('trash')"
      >
        {{ t("maintenance.recycle.tabTrash") }}
        <span class="recycle__hint">{{ t("maintenance.recycle.tabTrashHint") }}</span>
      </Button>
      <Button
        :variant="!isTrash ? 'tonal' : 'outlined'"
        size="compact"
        data-testid="recycle-tab-expunged"
        @click="setTab('expunged')"
      >
        {{ t("maintenance.recycle.tabExpunged") }}
        <span class="recycle__hint">{{ t("maintenance.recycle.tabExpungedHint") }}</span>
      </Button>
    </div>

    <div class="recycle__toolbar">
      <Button v-if="isTrash" data-testid="recycle-restore" :disabled="!selectedCount" @click="restore">
        {{ t("maintenance.recycle.restore") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
      <Button
        v-else
        data-testid="recycle-redownload"
        :disabled="!selectedCount"
        @click="redownload"
      >
        {{ t("maintenance.recycle.redownload") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
      <Button
        variant="outlined"
        class="recycle__danger"
        data-testid="recycle-purge"
        :disabled="!selectedCount"
        @click="openPurge"
      >
        {{ t("maintenance.recycle.purge") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
    </div>

    <div v-if="loading" class="recycle__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 8" :key="index" variant="card" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!items.length"
      :title="t('maintenance.recycle.empty')"
      testid="recycle-empty"
    />

    <div v-else class="recycle__grid">
      <div
        v-for="item in items"
        :key="item.id"
        class="recycle__card"
        :data-testid="`recycle-item-${item.id}`"
      >
        <GalleryThumb :src="item.cover_url" :alt="itemTitle(item)" size="card" />
        <label class="recycle__check">
          <input
            type="checkbox"
            :checked="selected.includes(item.id)"
            :aria-label="t('maintenance.shared.select')"
            :data-testid="`recycle-select-${item.id}`"
            @change="toggle(item.id)"
          />
          <span class="recycle__card-title">{{ itemTitle(item) }}</span>
        </label>
        <p class="recycle__meta">
          <span>{{ t("maintenance.recycle.pages", { n: item.page_count }) }}</span>
          <span v-if="itemDate(item)">{{ itemDate(item) }}</span>
          <span v-if="item.storage_path" class="recycle__path">{{ item.storage_path }}</span>
        </p>
        <RouterLink
          v-if="!isTrash"
          class="recycle__link"
          :to="{ name: 'gallery', params: { id: item.id } }"
        >
          #{{ item.id }}
        </RouterLink>
      </div>
    </div>

    <PagerBar
      v-if="total > pageSize"
      :page="page"
      :pages="pages"
      :total="total"
      testid="recycle-pager"
      @change="goPage"
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
      <label class="recycle__files">
        <input v-model="deleteFiles" type="checkbox" data-testid="recycle-delete-files" />
        {{ t("maintenance.recycle.deleteFiles") }}
      </label>
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

.recycle__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.recycle__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.recycle__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.recycle__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.recycle__tabs,
.recycle__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.recycle__hint {
  margin-left: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.recycle__danger {
  border-color: var(--gv-color-error);
  color: var(--gv-color-error);
}

.recycle__skeletons,
.recycle__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--gv-space-3);
}

.recycle__card {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.recycle__check {
  display: flex;
  align-items: flex-start;
  gap: var(--gv-space-1);
}

.recycle__card-title {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.recycle__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.recycle__path {
  overflow: hidden;
  width: 100%;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recycle__link {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  text-decoration: none;
}

.recycle__files {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-3);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}
</style>
