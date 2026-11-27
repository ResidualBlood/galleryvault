<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Icon from "@/components/icons/Icon.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import {
  cancelArchive,
  fetchArchiveState,
  restoreArchives,
  startArchive,
  type ArchiveState,
} from "@/api/archive";
import { fetchGalleries, type GalleryItem } from "@/api/library";
import { purgeArchivedSources } from "@/api/system";
import { ApiError } from "@/api/client";
import { ensureSystemMessages } from "@/components/system/messages";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";
import { useUiStore } from "@/stores/ui";

ensureSystemMessages();
ensureMaintenanceMessages();

const { t } = useI18n();
const router = useRouter();
const ui = useUiStore();
/** The maintenance tab strip only makes sense when the sibling routes exist. */
const hasMaintenanceTabs = computed(() => router.hasRoute("recycle") && router.hasRoute("duplicates"));
const state = ref<ArchiveState>({});
const loading = ref(true);
const busy = ref(false);
const loadError = ref("");
const purgeOpen = ref(false);
const purgeBusy = ref(false);
let timer: number | null = null;

const running = computed(() => Boolean(state.value.running));
const done = computed(() => Number(state.value.done) || 0);
const skipped = computed(() => Number(state.value.skipped) || 0);
const failed = computed(() => Number(state.value.failed) || 0);
const total = computed(() => Number(state.value.total) || 0);
const processed = computed(() => done.value + skipped.value + failed.value);
const percent = computed(() =>
  total.value > 0 ? Math.min(100, Math.round((processed.value / total.value) * 100)) : 0,
);
const hasHistory = computed(
  () => Boolean(state.value.started_at || state.value.completed_at) || total.value > 0,
);
const statusKey = computed(() => {
  if (running.value) return "running";
  if (failed.value > 0) return "failed";
  if (hasHistory.value) return "done";
  return "idle";
});
const statusLabel = computed(() => t(`system.archive.status.${statusKey.value}`));
const statusIcon = computed(() => {
  if (statusKey.value === "running") return "status-info";
  if (statusKey.value === "failed") return "status-error";
  if (statusKey.value === "done") return "status-success";
  return "archive";
});

const stats = computed(() => [
  { key: "done", value: done.value, icon: "status-success" as const, tone: "success" },
  { key: "skipped", value: skipped.value, icon: "status-info" as const, tone: "neutral" },
  { key: "failed", value: failed.value, icon: "status-error" as const, tone: "error" },
  { key: "total", value: total.value, icon: "archive" as const, tone: "neutral" },
]);

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function report(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

async function load(silent = false): Promise<void> {
  try {
    state.value = await fetchArchiveState();
    if (!silent) loadError.value = "";
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 401)) {
      const message = report(cause);
      if (silent) ui.error(message);
      else loadError.value = message;
    }
  } finally {
    loading.value = false;
    schedule();
  }
}

function schedule(): void {
  if (timer !== null) {
    window.clearTimeout(timer);
    timer = null;
  }
  if (running.value) timer = window.setTimeout(() => void load(true), 2000);
}

async function start(): Promise<void> {
  busy.value = true;
  try {
    const result = await startArchive();
    if (result.status === "paused") {
      ui.error(result.detail ?? t("system.archive.startFailed"));
    } else {
      ui.success(t("system.archive.started"));
      state.value = { ...state.value, running: true };
      schedule();
    }
  } catch (cause) {
    ui.error(
      cause instanceof ApiError && cause.status === 422
        ? t("system.archive.startFailed")
        : report(cause),
    );
  } finally {
    busy.value = false;
  }
}

async function cancel(): Promise<void> {
  busy.value = true;
  try {
    await cancelArchive();
    ui.success(t("system.archive.cancelled"));
    await load();
  } catch (cause) {
    ui.error(report(cause));
  } finally {
    busy.value = false;
  }
}

async function purge(): Promise<void> {
  purgeBusy.value = true;
  try {
    await purgeArchivedSources();
    purgeOpen.value = false;
    ui.success(t("system.global.purgeStarted"));
  } catch (cause) {
    ui.error(report(cause));
  } finally {
    purgeBusy.value = false;
  }
}

/* ------------------------------------------------------- cold library (T4.4) */

const COLD_PAGE_SIZE = 100;
const COLD_POLL_MS = 2500;
const COLD_MAX_POLLS = 24;

const coldItems = ref<GalleryItem[]>([]);
const coldTotal = ref(0);
const coldLoading = ref(true);
const coldError = ref("");
const coldSelected = ref<Set<number>>(new Set());
const restoreOpen = ref(false);
const restoreBusy = ref(false);
const restoreError = ref("");
const pendingCold = ref<number[]>([]);
let coldTimer: number | null = null;
let coldPolls = 0;

function formatSize(value?: number | null): string {
  const bytes = Number(value) || 0;
  if (bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 || size >= 10 ? 0 : 1)} ${units[unit]}`;
}

async function loadCold(silent = false): Promise<void> {
  try {
    const data = await fetchGalleries({
      storage_tier: "cold",
      page_size: COLD_PAGE_SIZE,
      order_by: "id_desc",
    });
    coldItems.value = data.items ?? [];
    coldTotal.value = Number(data.total) || coldItems.value.length;
    if (!silent) coldError.value = "";
    const visible = new Set(coldItems.value.map((item) => item.id));
    coldSelected.value = new Set(
      [...coldSelected.value].filter((id) => visible.has(id)),
    );
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 401)) {
      const message = report(cause);
      if (silent) ui.error(message);
      else coldError.value = message;
    }
  } finally {
    coldLoading.value = false;
  }
}

function toggleCold(id: number, checked: boolean): void {
  const next = new Set(coldSelected.value);
  if (checked) next.add(id);
  else next.delete(id);
  coldSelected.value = next;
}

function clearColdSelection(): void {
  coldSelected.value = new Set();
}

function viewCold(): void {
  void router.push({ name: "library", query: { storage_tier: "cold" } });
}

function openRestore(): void {
  restoreError.value = "";
  restoreOpen.value = true;
}

/** Unarchive runs in the background; refresh the cold list until the ids leave. */
function scheduleColdPoll(): void {
  if (coldTimer !== null) {
    window.clearTimeout(coldTimer);
    coldTimer = null;
  }
  if (!pendingCold.value.length || coldPolls >= COLD_MAX_POLLS) {
    pendingCold.value = [];
    return;
  }
  coldPolls += 1;
  coldTimer = window.setTimeout(async () => {
    await loadCold(true);
    const remaining = new Set(coldItems.value.map((item) => item.id));
    pendingCold.value = pendingCold.value.filter((id) => remaining.has(id));
    scheduleColdPoll();
  }, COLD_POLL_MS);
}

async function restoreSelected(): Promise<void> {
  const ids = [...coldSelected.value];
  if (!ids.length || restoreBusy.value) return;
  restoreBusy.value = true;
  restoreError.value = "";
  try {
    const result = await restoreArchives(ids);
    if (result.status === "paused") {
      restoreError.value = result.detail ?? t("system.archive.restoreFailed");
      return;
    }
    ui.success(t("system.archive.restoreStarted", { n: ids.length }));
    restoreOpen.value = false;
    coldSelected.value = new Set();
    pendingCold.value = ids;
    coldPolls = 0;
    scheduleColdPoll();
  } catch (cause) {
    restoreError.value = report(cause);
  } finally {
    restoreBusy.value = false;
  }
}

onMounted(() => {
  void load();
  void loadCold();
});
onBeforeUnmount(() => {
  if (timer !== null) window.clearTimeout(timer);
  if (coldTimer !== null) window.clearTimeout(coldTimer);
});
</script>

<template>
  <section class="archive" data-testid="archive-page">
    <PageHeader
      :title="t('system.archive.title')"
      :subtitle="t('system.archive.subtitle')"
      testid="archive-header"
    />

    <MaintenanceTabs v-if="hasMaintenanceTabs" active="archive" />

    <Toolbar testid="archive-toolbar" size="lg">
      <ToolbarGroup>
        <Button
          icon="archive"
          :disabled="busy || running"
          :loading="busy"
          data-testid="archive-start"
          @click="start"
        >
          {{ t("system.archive.start") }}
        </Button>
        <Button
          variant="outlined"
          icon="close"
          :disabled="busy || !running"
          data-testid="archive-cancel"
          @click="cancel"
        >
          {{ t("system.archive.cancel") }}
        </Button>
      </ToolbarGroup>
      <ToolbarGroup end collapsible :label="t('system.archive.purge')">
        <Button variant="text" icon="delete" data-testid="archive-purge" @click="purgeOpen = true">
          {{ t("system.archive.purge") }}
        </Button>
      </ToolbarGroup>
    </Toolbar>

    <section class="archive__panel" data-testid="archive-status">
      <div v-if="loading" class="archive__skeletons" aria-hidden="true">
        <Skeleton variant="line" :lines="3" />
      </div>

      <ErrorState
        v-else-if="loadError"
        testid="archive-error"
        :title="t('common.errorTitle')"
        :body="loadError"
        :retry-label="t('system.archive.loadFailedRetry')"
        @retry="load"
      />

      <template v-else>
        <div class="archive__status-row">
          <span class="archive__status" :data-state="statusKey" role="status">
            <Icon :name="statusIcon" size="dense" />
            <span>{{ statusLabel }}</span>
          </span>
        </div>

        <dl class="archive__times">
          <div class="archive__time">
            <dt>{{ t("system.archive.startedAt") }}</dt>
            <dd>{{ formatTime(state.started_at) }}</dd>
          </div>
          <div class="archive__time">
            <dt>{{ t("system.archive.completedAt") }}</dt>
            <dd>{{ formatTime(state.completed_at) }}</dd>
          </div>
        </dl>

        <div class="archive__progress-row">
          <span class="archive__progress-label">
            {{ t("system.archive.progress", { done: processed, total }) }}
          </span>
          <span class="archive__progress-percent">{{ percent }}%</span>
        </div>
        <div
          class="archive__progress"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="percent"
          :aria-label="t('system.archive.progressLabel')"
        >
          <div class="archive__progress-bar" :style="{ width: `${percent}%` }" />
        </div>

        <dl class="archive__stats">
          <div v-for="stat in stats" :key="stat.key" class="archive__stat" :data-tone="stat.tone">
            <dt>
              <Icon :name="stat.icon" size="dense" />
              <span>{{ t(`system.archive.${stat.key}`) }}</span>
            </dt>
            <dd>{{ stat.value }}</dd>
          </div>
        </dl>

        <EmptyState
          v-if="!hasHistory && !running"
          icon="archive"
          :title="t('system.archive.emptyTitle')"
          :body="t('system.archive.emptyBody')"
          :action-label="t('system.archive.start')"
          testid="archive-empty"
          @action="start"
        />

        <p v-if="state.last_error" class="archive__error" role="alert">
          {{ t("system.archive.lastError") }}: {{ state.last_error }}
        </p>
      </template>
    </section>

    <section class="archive__cold" data-testid="archive-cold">
      <div class="archive__cold-head">
        <div class="archive__cold-heading">
          <h2 class="archive__cold-title">{{ t("system.archive.coldTitle") }}</h2>
          <p class="archive__cold-count" data-testid="archive-cold-count">
            {{ t("system.archive.coldCount", { n: coldTotal }) }}
          </p>
        </div>
        <Button
          variant="outlined"
          icon="library"
          data-testid="archive-cold-view"
          @click="viewCold"
        >
          {{ t("system.archive.viewCold") }}
        </Button>
      </div>

      <ErrorState
        v-if="coldError"
        testid="archive-cold-error"
        :title="t('common.errorTitle')"
        :body="coldError"
        :retry-label="t('common.retry')"
        @retry="loadCold"
      />

      <div v-else-if="coldLoading" class="archive__cold-skeletons" aria-hidden="true">
        <Skeleton variant="line" :lines="3" />
      </div>

      <EmptyState
        v-else-if="!coldItems.length"
        icon="archive"
        :title="t('system.archive.coldEmptyTitle')"
        :body="t('system.archive.coldEmptyBody')"
        testid="archive-cold-empty"
      />

      <template v-else>
        <SelectionBar
          :count="coldSelected.size"
          testid="archive-cold-selection"
          @clear="clearColdSelection"
        >
          <Button
            variant="outlined"
            icon="archive"
            :loading="restoreBusy"
            :disabled="restoreBusy"
            data-testid="archive-cold-restore"
            @click="openRestore"
          >
            {{ t("system.archive.restoreSelected") }}
          </Button>
        </SelectionBar>

        <ul class="archive__cold-list" data-testid="archive-cold-list">
          <li
            v-for="item in coldItems"
            :key="item.id"
            class="archive__cold-row"
            :data-id="item.id"
            data-testid="archive-cold-row"
          >
            <Checkbox
              :model-value="coldSelected.has(item.id)"
              :aria-label="item.title"
              @update:model-value="toggleCold(item.id, $event)"
            />
            <span class="archive__cold-name" :title="item.title">{{ item.title }}</span>
            <span class="archive__cold-meta">
              {{ t("system.archive.coldPages", { n: item.page_count }) }}
              · {{ formatSize(item.storage_size ?? item.file_size) }}
            </span>
          </li>
        </ul>
      </template>
    </section>

    <Dialog
      :open="restoreOpen"
      :title="t('system.archive.restoreConfirmTitle')"
      testid="archive-cold-restore-dialog"
      @close="restoreOpen = false"
    >
      <p class="archive__dialog-body">
        {{ t("system.archive.restoreConfirmBody", { n: coldSelected.size }) }}
      </p>
      <p v-if="restoreError" class="archive__error" role="alert">{{ restoreError }}</p>
      <template #footer>
        <Button variant="text" :disabled="restoreBusy" @click="restoreOpen = false">
          {{ t("common.cancel") }}
        </Button>
        <Button
          :loading="restoreBusy"
          :disabled="restoreBusy"
          data-testid="archive-cold-restore-confirm"
          @click="restoreSelected"
        >
          {{ t("system.archive.restoreSelected") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="purgeOpen"
      :title="t('system.archive.confirmPurgeTitle')"
      @close="purgeOpen = false"
    >
      <p class="archive__dialog-body">{{ t("system.archive.confirmPurgeBody") }}</p>
      <template #footer>
        <Button variant="text" @click="purgeOpen = false">{{ t("common.cancel") }}</Button>
        <Button
          :loading="purgeBusy"
          :disabled="purgeBusy"
          data-testid="archive-purge-confirm"
          @click="purge"
        >
          {{ t("system.archive.purge") }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.archive {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.archive__panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-5);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
}

.archive__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.archive__status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
  flex-wrap: wrap;
}

.archive__status {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  height: var(--gv-size-chip);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.archive__status[data-state="running"] {
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.archive__status[data-state="done"] {
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
}

.archive__status[data-state="failed"] {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.archive__times {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2) var(--gv-space-6);
  margin: 0;
}

.archive__time {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
  min-width: 0;
}

.archive__time dt {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.archive__time dd {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
}

.archive__progress-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-3);
}

.archive__progress-label {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
}

.archive__progress-percent {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
  font-variant-numeric: tabular-nums;
}

.archive__progress {
  height: var(--gv-space-2);
  overflow: hidden;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container-highest);
}

.archive__progress-bar {
  height: 100%;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  transition: width var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.archive__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--gv-space-2);
  margin: 0;
}

.archive__stat {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-low);
}

.archive__stat dt {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.archive__stat dd {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-large);
  font-variant-numeric: tabular-nums;
}

.archive__stat[data-tone="error"] dd {
  color: var(--gv-color-error);
}

.archive__stat[data-tone="success"] dd {
  color: var(--gv-color-success);
}

.archive__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.archive__dialog-body {
  margin: 0;
  font: var(--gv-type-body-medium);
}

.archive__cold {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-5);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
}

.archive__cold-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
}

.archive__cold-heading {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.archive__cold-title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.archive__cold-count {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
}

.archive__cold-skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.archive__cold-list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  max-height: 360px;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.archive__cold-row {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  min-height: var(--gv-size-control-md);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
}

.archive__cold-row:hover {
  background: var(--gv-color-surface-container-low);
}

.archive__cold-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.archive__cold-meta {
  flex: none;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 599.98px) {
  .archive {
    gap: var(--gv-space-4);
  }

  .archive__panel {
    padding: var(--gv-space-4);
  }
}
</style>
