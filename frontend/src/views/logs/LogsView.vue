<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Icon from "@/components/icons/Icon.vue";
import Input from "@/components/ui/Input.vue";
import Pager from "@/components/ui/Pager.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import Tabs from "@/components/ui/Tabs.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import {
  cancelBackgroundTask,
  clearSystemLogs,
  fetchBackgroundLogs,
  fetchSystemLogs,
  setSystemLogLevel,
  systemLogsDownloadUrl,
  type BackgroundLogs,
  type FinishedTask,
  type SystemLogPage,
} from "@/api/system";
import { ensureSystemMessages } from "@/components/system/messages";
import { useUiStore } from "@/stores/ui";

ensureSystemMessages();

type Tab = "activity" | "system";
type FinishedFilter = "all" | "failed";
type TaskStatus = "success" | "failed" | "cancelled" | "running" | "unknown";

const FINISHED_PAGE_SIZE = 50;

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const { t } = useI18n();
const tab = ref<Tab>(route.query.tab === "system" ? "system" : "activity");
const activity = ref<BackgroundLogs>({ running: [], finished: [] });
const activityError = ref("");
const system = ref<SystemLogPage>({ logs: [] });
const systemError = ref("");
const runtimeLevel = ref("INFO");
const minLevel = ref("INFO");
const search = ref("");
const autoScroll = ref(true);
const cancelling = ref<string | null>(null);
const clearOpen = ref(false);
const clearBusy = ref(false);
const finishedFilter = ref<FinishedFilter>("all");
const finishedPage = ref(1);
const hiddenFinished = ref<string[]>([]);
const listEl = ref<HTMLElement | null>(null);
const tabsHost = ref<HTMLElement | null>(null);
let activityTimer: number | null = null;
let systemTimer: number | null = null;

const tabs = computed(() => [
  { value: "activity", label: t("system.logs.tabActivity"), icon: "history" as const },
  { value: "system", label: t("system.logs.tabSystem"), icon: "logs" as const },
]);

const levelOptions = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map((value) => ({
  value,
  label: value,
}));
const filterOptions = ["DEBUG", "INFO", "WARNING", "ERROR"].map((value) => ({
  value,
  label: `${value}+`,
}));
const finishedFilterOptions = computed(() => [
  { value: "all", label: t("system.logs.filterAll") },
  { value: "failed", label: t("system.logs.filterFailed") },
]);

const running = computed(() => activity.value.running ?? []);
const finished = computed(() => activity.value.finished ?? []);

function finishedKey(task: FinishedTask): string {
  return `${task.task}|${task.started_at ?? ""}|${task.completed_at ?? ""}`;
}

function statusOf(task: { status?: string }): TaskStatus {
  const value = (task.status ?? "").toLowerCase();
  if (["success", "done", "completed"].includes(value)) return "success";
  if (["failed", "error"].includes(value)) return "failed";
  if (["cancelled", "canceled"].includes(value)) return "cancelled";
  if (value === "running") return "running";
  return "unknown";
}

function statusLabel(task: { status?: string }): string {
  return t(`system.logs.taskStatus.${statusOf(task)}`);
}

function statusIcon(task: { status?: string }): "status-success" | "status-error" | "status-blocked" | "status-info" {
  const status = statusOf(task);
  if (status === "success") return "status-success";
  if (status === "failed") return "status-error";
  if (status === "cancelled") return "status-blocked";
  return "status-info";
}

function progressText(task: { done?: number | null; total?: number | null }): string {
  const total = task.total;
  const done = task.done ?? 0;
  if (total === null || total === undefined) return done ? String(done) : "—";
  if (total <= 0) return `${done} / 0`;
  return `${Math.min(done, total)} / ${total}`;
}

function progressPercent(task: { done?: number | null; total?: number | null }): number {
  if (!task.total || task.total <= 0) return 0;
  return Math.min(100, Math.round(((task.done ?? 0) / task.total) * 100));
}

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDuration(
  task: { started_at?: string | null; completed_at?: string | null },
): string {
  if (!task.started_at) return "—";
  const start = new Date(task.started_at).getTime();
  const end = task.completed_at ? new Date(task.completed_at).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "—";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

const finishedVisible = computed(() =>
  finished.value.filter((task) => {
    if (hiddenFinished.value.includes(finishedKey(task))) return false;
    if (finishedFilter.value === "failed" && statusOf(task) !== "failed") return false;
    return true;
  }),
);
const finishedPages = computed(() =>
  Math.max(1, Math.ceil(finishedVisible.value.length / FINISHED_PAGE_SIZE)),
);
const finishedPageItems = computed(() => {
  const page = Math.min(finishedPage.value, finishedPages.value);
  const start = (page - 1) * FINISHED_PAGE_SIZE;
  return finishedVisible.value.slice(start, start + FINISHED_PAGE_SIZE);
});

async function loadActivity(): Promise<void> {
  try {
    activity.value = await fetchBackgroundLogs();
    activityError.value = "";
  } catch (cause) {
    activityError.value = cause instanceof Error ? cause.message : t("system.logs.loadFailed");
  }
}

async function loadSystem(): Promise<void> {
  try {
    const page = await fetchSystemLogs({ minLevel: minLevel.value, search: search.value });
    system.value = page;
    runtimeLevel.value = page.level ?? runtimeLevel.value;
    systemError.value = "";
    await nextTick();
    if (autoScroll.value && listEl.value) listEl.value.scrollTop = 0;
  } catch (cause) {
    systemError.value = cause instanceof Error ? cause.message : t("system.logs.loadSystemFailed");
  }
}

function scheduleActivity(): void {
  if (activityTimer !== null) window.clearInterval(activityTimer);
  activityTimer = window.setInterval(() => void loadActivity(), 5000);
}

function scheduleSystem(): void {
  if (systemTimer !== null) window.clearInterval(systemTimer);
  systemTimer = window.setInterval(() => void loadSystem(), 5000);
}

function selectTab(value: string): void {
  const next: Tab = value === "system" ? "system" : "activity";
  tab.value = next;
  const query = { ...route.query };
  if (next === "system") query.tab = "system";
  else delete query.tab;
  void router.replace({ query });
}

function clearFinished(): void {
  hiddenFinished.value = [
    ...new Set([...hiddenFinished.value, ...finished.value.map(finishedKey)]),
  ];
  finishedPage.value = 1;
  ui.success(t("system.logs.clearedFinished"));
}

async function cancelTask(task: string): Promise<void> {
  cancelling.value = task;
  try {
    await cancelBackgroundTask(task);
    await loadActivity();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    cancelling.value = null;
  }
}

async function changeRuntimeLevel(level: string): Promise<void> {
  try {
    const result = await setSystemLogLevel(level);
    runtimeLevel.value = result.level ?? level;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function confirmClear(): Promise<void> {
  clearBusy.value = true;
  try {
    await clearSystemLogs();
    clearOpen.value = false;
    ui.success(t("system.logs.cleared"));
    await loadSystem();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    clearBusy.value = false;
  }
}

function downloadLogs(): void {
  const anchor = document.createElement("a");
  anchor.href = systemLogsDownloadUrl();
  anchor.download = "";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

function entryContext(entry: { context?: Record<string, unknown> | null }): string {
  if (!entry.context || !Object.keys(entry.context).length) return "";
  try {
    return JSON.stringify(entry.context);
  } catch {
    return "";
  }
}

/**
 * The shared Tabs component has no per-item test id, while the parity suite
 * clicks `logs-tab-activity` / `logs-tab-system`. Tag the rendered tab buttons
 * once they exist instead of adding a second, hand-written tab strip.
 */
function tagTabs(): void {
  const buttons = tabsHost.value?.querySelectorAll<HTMLElement>("[data-tab-value]");
  buttons?.forEach((button) => {
    const value = button.dataset.tabValue;
    if (value) button.dataset.testid = `logs-tab-${value}`;
  });
}

watch(tab, (value) => {
  if (value === "system") void loadSystem();
  else void loadActivity();
});

watch(finishedFilter, () => {
  finishedPage.value = 1;
});

watch([minLevel, search], () => {
  if (tab.value === "system") void loadSystem();
});

onMounted(() => {
  tagTabs();
  void loadActivity();
  void loadSystem();
  scheduleActivity();
  scheduleSystem();
});

onUpdated(tagTabs);

onBeforeUnmount(() => {
  if (activityTimer !== null) window.clearInterval(activityTimer);
  if (systemTimer !== null) window.clearInterval(systemTimer);
});
</script>

<template>
  <section class="logs" data-testid="logs-page">
    <PageHeader
      :title="t('system.logs.title')"
      :subtitle="t('system.logs.subtitle')"
      testid="logs-header"
    />

    <div ref="tabsHost">
      <Tabs
        :items="tabs"
        :model-value="tab"
        :label="t('system.logs.title')"
        testid="logs-tabs"
        @update:model-value="selectTab"
      />
    </div>

    <section v-if="tab === 'activity'" class="logs__panel" data-testid="logs-activity">
      <Toolbar testid="logs-activity-toolbar" size="sm">
        <ToolbarGroup>
          <SegmentedControl
            v-model="finishedFilter"
            :options="finishedFilterOptions"
            :label="t('system.logs.finished')"
            testid="logs-filter"
          />
        </ToolbarGroup>
        <ToolbarGroup end collapsible :label="t('system.logs.actions')">
          <Button icon="retry" data-testid="logs-refresh" @click="loadActivity">
            {{ t("system.logs.refresh") }}
          </Button>
          <Button
            variant="text"
            icon="clear"
            :disabled="!finishedVisible.length"
            data-testid="logs-clear-finished"
            @click="clearFinished"
          >
            {{ t("system.logs.clearFinished") }}
          </Button>
        </ToolbarGroup>
      </Toolbar>

      <ErrorState
        v-if="activityError"
        testid="logs-activity-error"
        :title="t('common.errorTitle')"
        :body="activityError"
        :retry-label="t('system.logs.refresh')"
        @retry="loadActivity"
      />

      <section v-if="running.length" class="logs__section">
        <header class="logs__section-head">
          <h2 class="logs__section-title">{{ t("system.logs.running") }}</h2>
          <span class="logs__section-count">{{ running.length }}</span>
        </header>
        <ul class="logs__tasks">
          <li
            v-for="task in running"
            :key="task.task"
            class="logs__task logs__task--running"
            :data-task="task.task"
            data-testid="logs-running-row"
          >
            <span class="logs__task-status" data-status="running">
              <Icon name="status-info" size="dense" />
              <span>{{ t("system.logs.taskStatus.running") }}</span>
            </span>
            <span class="logs__task-name">{{ task.task }}</span>
            <span class="logs__task-progress">
              <span class="logs__progress-track" aria-hidden="true">
                <span
                  class="logs__progress-fill"
                  :style="{ width: `${progressPercent(task)}%` }"
                />
              </span>
              <span>{{ progressText(task) }}</span>
            </span>
            <span class="logs__task-meta">{{ task.stage || formatTime(task.started_at) }}</span>
            <Button
              v-if="task.cancellable"
              variant="outlined"
              icon="close"
              :disabled="cancelling === task.task"
              data-testid="logs-cancel"
              @click="cancelTask(task.task)"
            >
              {{ cancelling === task.task ? t("system.logs.cancelling") : t("system.logs.cancel") }}
            </Button>
          </li>
        </ul>
      </section>

      <section class="logs__section">
        <header class="logs__section-head">
          <h2 class="logs__section-title">{{ t("system.logs.finished") }}</h2>
          <span class="logs__section-count">{{ finishedVisible.length }}</span>
        </header>

        <EmptyState
          v-if="!finishedVisible.length"
          icon="logs"
          :title="t('system.logs.noFinished')"
          :body="t('system.logs.noFinishedBody')"
          :action-label="t('system.logs.refresh')"
          testid="logs-finished-empty"
          @action="loadActivity"
        />

        <template v-else>
          <ul class="logs__tasks logs__tasks--scroll" data-testid="logs-finished-list">
            <li
              v-for="task in finishedPageItems"
              :key="finishedKey(task)"
              class="logs__task"
              :data-status="statusOf(task)"
              data-testid="logs-finished-row"
            >
              <span class="logs__task-status" :data-status="statusOf(task)">
                <Icon :name="statusIcon(task)" size="dense" />
                <span>{{ statusLabel(task) }}</span>
              </span>
              <span class="logs__task-name">{{ task.task }}</span>
              <span class="logs__task-progress">{{ progressText(task) }}</span>
              <span class="logs__task-meta">
                <span>{{ formatTime(task.started_at) }}</span>
                <span>·</span>
                <span>{{ t("system.logs.duration", { duration: formatDuration(task) }) }}</span>
              </span>
            </li>
          </ul>

          <Pager
            v-if="finishedPages > 1"
            :page="Math.min(finishedPage, finishedPages)"
            :total-pages="finishedPages"
            testid="logs-finished-pager"
            @update:page="finishedPage = $event"
          />
        </template>
      </section>
    </section>

    <section v-else class="logs__panel" data-testid="logs-system">
      <Toolbar testid="syslog-toolbar" size="sm">
        <ToolbarGroup>
          <Select
            v-model="runtimeLevel"
            class="logs__level-select"
            :options="levelOptions"
            :aria-label="t('system.logs.level')"
            data-testid="syslog-level"
            @change="changeRuntimeLevel"
          />
        </ToolbarGroup>
        <ToolbarGroup>
          <Select
            v-model="minLevel"
            class="logs__filter-select"
            :options="filterOptions"
            :aria-label="t('system.logs.filterLevel')"
            data-testid="syslog-filter"
          />
        </ToolbarGroup>
        <ToolbarGroup>
          <Input
            v-model="search"
            class="logs__search"
            type="search"
            :placeholder="t('system.logs.searchPlaceholder')"
            :aria-label="t('system.logs.searchPlaceholder')"
            data-testid="syslog-search"
          />
        </ToolbarGroup>
        <ToolbarGroup>
          <label class="logs__autoscroll">
            <Switch
              v-model="autoScroll"
              :label="t('system.logs.autoScroll')"
              data-testid="syslog-autoscroll"
            />
            <span>{{ t("system.logs.autoScroll") }}</span>
          </label>
        </ToolbarGroup>
        <ToolbarGroup end collapsible :label="t('system.logs.actions')">
          <Button icon="downloads" data-testid="syslog-download" @click="downloadLogs">
            {{ t("system.logs.download") }}
          </Button>
          <Button icon="retry" data-testid="syslog-refresh" @click="loadSystem">
            {{ t("system.logs.refresh") }}
          </Button>
          <Button
            variant="text"
            icon="clear"
            data-testid="syslog-clear"
            @click="clearOpen = true"
          >
            {{ t("system.logs.clear") }}
          </Button>
        </ToolbarGroup>
      </Toolbar>

      <p class="logs__meta">
        {{
          t("system.logs.storageInfo", {
            mode: system.log_mode ?? "memory",
            count: system.logs.length,
          })
        }}
      </p>

      <ErrorState
        v-if="systemError"
        testid="logs-system-error"
        :title="t('common.errorTitle')"
        :body="systemError"
        :retry-label="t('system.logs.refresh')"
        @retry="loadSystem"
      />

      <ol ref="listEl" class="logs__list" data-testid="syslog-list">
        <li
          v-for="entry in system.logs"
          :key="entry.id"
          class="logs__entry"
          :data-level="entry.level"
          data-testid="syslog-entry"
        >
          <span class="logs__level" :data-level="entry.level">{{ entry.level }}</span>
          <span class="logs__time">{{ entry.time }}</span>
          <span class="logs__logger">{{ entry.logger }}</span>
          <span class="logs__message">{{ entry.message }}</span>
          <span v-if="entryContext(entry)" class="logs__context">{{ entryContext(entry) }}</span>
        </li>
        <li v-if="!system.logs.length" class="logs__empty">{{ t("system.logs.empty") }}</li>
      </ol>
    </section>

    <Dialog :open="clearOpen" :title="t('system.logs.clearTitle')" @close="clearOpen = false">
      <p class="logs__dialog-body">{{ t("system.logs.clearBody") }}</p>
      <template #footer>
        <Button variant="text" @click="clearOpen = false">{{ t("common.cancel") }}</Button>
        <Button
          :loading="clearBusy"
          :disabled="clearBusy"
          data-testid="syslog-clear-confirm"
          @click="confirmClear"
        >
          {{ t("system.logs.clear") }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.logs {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.logs__panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  min-width: 0;
}

.logs__section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.logs__section-head {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
}

.logs__section-title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.logs__section-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--gv-space-5);
  height: var(--gv-space-5);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
  font-variant-numeric: tabular-nums;
}

.logs__tasks {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

/* LG2-01: the finished log is windowed — 50 rows per page stay inside this
 * scroll container so a long task history never stretches the document. */
.logs__tasks--scroll {
  max-height: 56vh;
  overflow-y: auto;
}

.logs__task {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr) 88px minmax(0, 220px);
  align-items: center;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-control-lg);
  padding: 0 var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface);
}

.logs__task:last-child {
  border-bottom: 0;
}

.logs__task--running {
  grid-template-columns: 108px minmax(0, 1fr) 132px minmax(0, 180px) auto;
}

.logs__task-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
}

.logs__task-status {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--gv-space-1);
  min-width: 0;
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.logs__task-status[data-status="success"] {
  color: var(--gv-color-success);
}

.logs__task-status[data-status="failed"] {
  color: var(--gv-color-error);
}

.logs__task-status[data-status="cancelled"] {
  color: var(--gv-color-on-surface-variant);
}

.logs__task-status[data-status="running"] {
  color: var(--gv-color-primary-text);
}

.logs__task-status[data-status="unknown"] {
  color: var(--gv-color-on-surface-variant);
}

.logs__task-progress {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.logs__progress-track {
  display: inline-flex;
  width: 44px;
  height: var(--gv-space-1);
  overflow: hidden;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container-highest);
}

.logs__progress-fill {
  height: 100%;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.logs__task-meta {
  display: inline-flex;
  gap: var(--gv-space-1);
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.logs__autoscroll {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.logs__level-select {
  width: 132px;
}

.logs__filter-select {
  width: 112px;
}

.logs__search {
  width: 220px;
}

.logs__meta {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  font-variant-numeric: tabular-nums;
}

.logs__list {
  margin: 0;
  padding: var(--gv-space-2);
  list-style: none;
  max-height: 62vh;
  overflow: auto;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-lowest);
}

.logs__entry {
  display: grid;
  grid-template-columns: 80px 200px minmax(120px, 200px) minmax(0, 1fr);
  gap: var(--gv-space-2);
  padding: var(--gv-space-1) 0;
  border-bottom: 1px solid var(--gv-color-outline-variant);
  color: var(--gv-color-on-surface);
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: var(--gv-type-body-small-size);
  line-height: var(--gv-type-body-small-line);
  font-variant-numeric: tabular-nums;
}

.logs__entry:last-child {
  border-bottom: 0;
}

.logs__level {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--gv-size-tag);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font-family: var(--gv-type-family-plain);
  font-size: var(--gv-type-label-small-size);
  font-weight: var(--gv-type-label-small-weight);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.logs__level[data-level="WARNING"] {
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
}

.logs__level[data-level="ERROR"],
.logs__level[data-level="CRITICAL"] {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.logs__time,
.logs__logger {
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  white-space: nowrap;
  text-overflow: ellipsis;
}

.logs__message {
  overflow-wrap: anywhere;
}

.logs__context {
  grid-column: 2 / -1;
  color: var(--gv-color-on-surface-variant);
  overflow-wrap: anywhere;
}

.logs__empty {
  padding: var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.logs__dialog-body {
  margin: 0;
  font: var(--gv-type-body-medium);
}

@media (max-width: 839.98px) {
  .logs__task,
  .logs__task--running {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      "status status"
      "name name"
      "progress meta";
    row-gap: var(--gv-space-1);
    padding: var(--gv-space-2) var(--gv-space-3);
  }

  .logs__task-status {
    grid-area: status;
  }

  .logs__task-name {
    grid-area: name;
  }

  .logs__task-progress {
    grid-area: progress;
  }

  .logs__task-meta {
    grid-area: meta;
    justify-content: flex-end;
  }

  .logs__task > .btn {
    grid-area: meta;
  }

  .logs__task--running .logs__task-meta {
    display: none;
  }

  .logs__level-select,
  .logs__filter-select {
    width: 132px;
  }

  .logs__search {
    width: 100%;
  }

  .logs__entry {
    grid-template-columns: 80px minmax(0, 1fr);
  }

  .logs__time,
  .logs__logger,
  .logs__message,
  .logs__context {
    grid-column: 2;
  }
}

@media (max-width: 599.98px) {
  .logs {
    gap: var(--gv-space-4);
  }

  /* Keep finished rows at 40px on a phone: status, name and time share one
   * line so 50 rows still read as a dense log. */
  .logs__task:not(.logs__task--running) {
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas: "status name meta";
    row-gap: 0;
    padding: 0 var(--gv-space-3);
  }

  .logs__task:not(.logs__task--running) .logs__task-progress {
    display: none;
  }

  .logs__task--running {
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "status name button"
      "progress progress progress";
  }

  .logs__task--running > .btn {
    grid-area: button;
  }
}
</style>
