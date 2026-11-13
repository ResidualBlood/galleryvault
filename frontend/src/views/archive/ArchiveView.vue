<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Icon from "@/components/icons/Icon.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import {
  cancelArchive,
  fetchArchiveState,
  startArchive,
  type ArchiveState,
} from "@/api/archive";
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

onMounted(() => void load());
onBeforeUnmount(() => {
  if (timer !== null) window.clearTimeout(timer);
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

@media (max-width: 599.98px) {
  .archive {
    gap: var(--gv-space-4);
  }

  .archive__panel {
    padding: var(--gv-space-4);
  }
}
</style>
