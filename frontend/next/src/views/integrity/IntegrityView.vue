<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import {
  fetchIntegrity,
  redownloadGallery,
  scanIntegrity,
  type IntegrityGallery,
  type IntegrityScanSummary,
} from "@/api/integrity";
import { useUiStore } from "@/stores/ui";
import { useSettingsStore } from "@/stores/settings";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import PagerBar from "@/views/updates/components/PagerBar.vue";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const { t } = useI18n();

const items = ref<IntegrityGallery[]>([]);
const total = ref(0);
const summary = ref<IntegrityScanSummary | null>(null);
const loading = ref(true);
const error = ref("");
const selected = ref<number[]>([]);
const scanning = ref(false);
const repairing = ref(false);
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

function itemTitle(item: IntegrityGallery): string {
  return item.title || `#${item.id}`;
}

function mismatch(item: IntegrityGallery): string {
  return t("maintenance.integrity.mismatch", {
    declared: item.page_count,
    actual: item.actual_pages,
    files: item.file_count ?? t("maintenance.integrity.fileUnknown"),
  });
}

function toggle(id: number): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id];
}

function selectAll(): void {
  selected.value = items.value.map((item) => item.id);
}

function clearSelection(): void {
  selected.value = [];
}

function goPage(next: number): void {
  void router.push({ name: "integrity", query: { page: next } });
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
    selected.value = [];
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    repairing.value = false;
  }
}

watch(
  () => [page.value, pageSize.value] as const,
  () => {
    selected.value = [];
    void load();
  },
  { immediate: true },
);
</script>

<template>
  <section class="integrity" data-testid="integrity-view">
    <header class="integrity__header">
      <p class="integrity__eyebrow">{{ t("maintenance.integrity.eyebrow") }}</p>
      <h1 class="integrity__title">{{ t("maintenance.integrity.title") }}</h1>
      <p class="integrity__subtitle">{{ t("maintenance.integrity.subtitle") }}</p>
      <p v-if="summary" class="integrity__summary" data-testid="integrity-summary">
        {{
          t("maintenance.integrity.scanSummary", {
            scanned: summary.scanned,
            total: summary.total,
            corrupt: summary.corrupt,
          })
        }}
      </p>
    </header>

    <MaintenanceTabs active="integrity" />

    <div class="integrity__toolbar">
      <Button variant="outlined" data-testid="integrity-scan" :loading="scanning" @click="scan">
        {{ t("maintenance.integrity.scan") }}
      </Button>
      <Button variant="outlined" data-testid="integrity-select-all" @click="selectAll">
        {{ t("maintenance.integrity.selectAll") }}
      </Button>
      <Button variant="outlined" data-testid="integrity-clear" @click="clearSelection">
        {{ t("maintenance.integrity.clear") }}
      </Button>
      <Button
        data-testid="integrity-repair"
        :disabled="!selectedCount"
        :loading="repairing"
        @click="repair"
      >
        {{ t("maintenance.integrity.repair") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
    </div>

    <details class="integrity__info">
      <summary>{{ t("maintenance.integrity.infoSummary") }}</summary>
      <p>{{ t("maintenance.integrity.infoDetail") }}</p>
    </details>

    <div v-if="loading" class="integrity__skeletons" aria-hidden="true">
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
      :title="t('maintenance.integrity.empty')"
      testid="integrity-empty"
    />

    <div v-else class="integrity__grid">
      <div
        v-for="item in items"
        :key="item.id"
        class="integrity__card"
        :data-testid="`integrity-item-${item.id}`"
      >
        <GalleryThumb :src="item.cover_url" :alt="itemTitle(item)" size="card" />
        <label class="integrity__check">
          <input
            type="checkbox"
            :checked="selected.includes(item.id)"
            :aria-label="t('maintenance.shared.select')"
            :data-testid="`integrity-select-${item.id}`"
            @change="toggle(item.id)"
          />
          <RouterLink
            class="integrity__card-title"
            :to="{ name: 'gallery', params: { id: item.id } }"
          >
            {{ itemTitle(item) }}
          </RouterLink>
        </label>
        <p class="integrity__mismatch">{{ mismatch(item) }}</p>
        <p v-if="item.storage_path" class="integrity__path">{{ item.storage_path }}</p>
      </div>
    </div>

    <PagerBar
      v-if="total > pageSize"
      :page="page"
      :pages="pages"
      :total="total"
      testid="integrity-pager"
      @change="goPage"
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

.integrity__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.integrity__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.integrity__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.integrity__subtitle,
.integrity__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.integrity__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.integrity__info {
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.integrity__info summary {
  cursor: pointer;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
}

.integrity__info p {
  margin: var(--gv-space-2) 0 0;
}

.integrity__skeletons,
.integrity__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--gv-space-3);
}

.integrity__card {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.integrity__check {
  display: flex;
  align-items: flex-start;
  gap: var(--gv-space-1);
}

.integrity__card-title {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
}

.integrity__mismatch {
  margin: 0;
  color: var(--gv-color-warning);
  font: var(--gv-type-body-small);
}

.integrity__path {
  overflow: hidden;
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
