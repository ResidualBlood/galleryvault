<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import {
  cancelBackgroundTask,
  clearSystemLogs,
  fetchBackgroundLogs,
  fetchSystemLogs,
  setSystemLogLevel,
  systemLogsDownloadUrl,
  type BackgroundLogs,
  type SystemLogPage,
} from "@/api/system";
import { ensureSystemMessages } from "@/components/system/messages";

ensureSystemMessages();

type Tab = "activity" | "system";

const { t } = useI18n();
const tab = ref<Tab>("activity");
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
const listEl = ref<HTMLElement | null>(null);
let activityTimer: number | null = null;
let systemTimer: number | null = null;

const levelOptions = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map((value) => ({
  value,
  label: value,
}));
const filterOptions = ["DEBUG", "INFO", "WARNING", "ERROR"].map((value) => ({
  value,
  label: `${value}+`,
}));

const running = computed(() => activity.value.running ?? []);
const finished = computed(() => activity.value.finished ?? []);

function progressText(done?: number | null, total?: number | null): string {
  if (total === null || total === undefined) return String(done ?? "");
  return `${done ?? 0} / ${total}`;
}

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

async function cancelTask(task: string): Promise<void> {
  cancelling.value = task;
  try {
    await cancelBackgroundTask(task);
    await loadActivity();
  } catch (cause) {
    activityError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    cancelling.value = null;
  }
}

async function changeRuntimeLevel(level: string): Promise<void> {
  try {
    const result = await setSystemLogLevel(level);
    runtimeLevel.value = result.level ?? level;
  } catch (cause) {
    systemError.value = cause instanceof Error ? cause.message : String(cause);
  }
}

async function confirmClear(): Promise<void> {
  clearBusy.value = true;
  try {
    await clearSystemLogs();
    clearOpen.value = false;
    await loadSystem();
  } catch (cause) {
    systemError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    clearBusy.value = false;
  }
}

function entryContext(entry: { context?: Record<string, unknown> | null }): string {
  if (!entry.context || !Object.keys(entry.context).length) return "";
  try {
    return JSON.stringify(entry.context);
  } catch {
    return "";
  }
}

watch(tab, (value) => {
  if (value === "system") void loadSystem();
  else void loadActivity();
});

watch([minLevel, search], () => {
  if (tab.value === "system") void loadSystem();
});

onMounted(() => {
  void loadActivity();
  void loadSystem();
  scheduleActivity();
  scheduleSystem();
});

onBeforeUnmount(() => {
  if (activityTimer !== null) window.clearInterval(activityTimer);
  if (systemTimer !== null) window.clearInterval(systemTimer);
});
</script>

<template>
  <div class="logs" data-testid="logs-page">
    <header class="logs__header">
      <h1 class="logs__title">{{ t('system.logs.title') }}</h1>
      <p class="logs__subtitle">{{ t('system.logs.subtitle') }}</p>
    </header>

    <div class="logs__tabs" role="tablist">
      <button
        type="button"
        class="logs__tab"
        :class="{ 'logs__tab--active': tab === 'activity' }"
        data-testid="logs-tab-activity"
        @click="tab = 'activity'"
      >
        {{ t('system.logs.tabActivity') }}
      </button>
      <button
        type="button"
        class="logs__tab"
        :class="{ 'logs__tab--active': tab === 'system' }"
        data-testid="logs-tab-system"
        @click="tab = 'system'"
      >
        {{ t('system.logs.tabSystem') }}
      </button>
    </div>

    <section v-if="tab === 'activity'" class="logs__panel" data-testid="logs-activity">
      <p v-if="activityError" class="logs__error" role="alert">{{ activityError }}</p>

      <h2 class="logs__section-title">{{ t('system.logs.running') }}</h2>
      <ul class="logs__tasks">
        <li v-for="task in running" :key="task.task" class="logs__task" :data-task="task.task">
          <div class="logs__task-main">
            <span class="logs__task-name">{{ task.task }}</span>
            <span class="logs__task-meta">
              {{ task.stage || t('system.logs.running') }} ·
              {{ progressText(task.done, task.total) }}
            </span>
          </div>
          <Button
            v-if="task.cancellable"
            variant="outlined"
            size="compact"
            :disabled="cancelling === task.task"
            data-testid="logs-cancel"
            @click="cancelTask(task.task)"
          >
            {{ cancelling === task.task ? t('system.logs.cancelling') : t('system.logs.cancel') }}
          </Button>
        </li>
        <li v-if="!running.length" class="logs__empty">{{ t('system.logs.noTasks') }}</li>
      </ul>

      <h2 class="logs__section-title">{{ t('system.logs.finished') }}</h2>
      <ul class="logs__tasks">
        <li v-for="(task, index) in finished" :key="`${task.task}-${index}`" class="logs__task">
          <div class="logs__task-main">
            <span class="logs__task-name">{{ task.task }}</span>
            <span class="logs__task-meta" :data-status="task.status">{{ task.status }}</span>
          </div>
          <span class="logs__task-meta">{{ progressText(task.done, task.total) }}</span>
        </li>
        <li v-if="!finished.length" class="logs__empty">{{ t('system.logs.noTasks') }}</li>
      </ul>
    </section>

    <section v-else class="logs__panel" data-testid="logs-system">
      <div class="logs__controls">
        <Select
          v-model="runtimeLevel"
          :options="levelOptions"
          :label="t('system.logs.level')"
          data-testid="syslog-level"
          @change="changeRuntimeLevel"
        />
        <Select
          v-model="minLevel"
          :options="filterOptions"
          :label="t('system.logs.filterLevel')"
          data-testid="syslog-filter"
        />
        <Input
          v-model="search"
          type="search"
          :placeholder="t('system.logs.searchPlaceholder')"
          data-testid="syslog-search"
        />
        <label class="logs__autoscroll">
          <Switch v-model="autoScroll" :label="t('system.logs.autoScroll')" data-testid="syslog-autoscroll" />
          <span>{{ t('system.logs.autoScroll') }}</span>
        </label>
        <a
          class="logs__download"
          :href="systemLogsDownloadUrl()"
          download
          data-testid="syslog-download"
        >
          {{ t('system.logs.download') }}
        </a>
        <Button variant="outlined" size="compact" @click="loadSystem">
          {{ t('system.logs.refresh') }}
        </Button>
        <Button variant="outlined" size="compact" data-testid="syslog-clear" @click="clearOpen = true">
          {{ t('system.logs.clear') }}
        </Button>
      </div>

      <p class="logs__meta">
        {{
          t('system.logs.storageInfo', {
            mode: system.log_mode ?? 'memory',
            count: system.logs.length,
          })
        }}
      </p>
      <p v-if="systemError" class="logs__error" role="alert">{{ systemError }}</p>

      <ol ref="listEl" class="logs__list" data-testid="syslog-list">
        <li v-for="entry in system.logs" :key="entry.id" class="logs__entry" :data-level="entry.level">
          <span class="logs__level" :data-level="entry.level">{{ entry.level }}</span>
          <span class="logs__time">{{ entry.time }}</span>
          <span class="logs__logger">{{ entry.logger }}</span>
          <span class="logs__message">{{ entry.message }}</span>
          <span v-if="entryContext(entry)" class="logs__context">{{ entryContext(entry) }}</span>
        </li>
        <li v-if="!system.logs.length" class="logs__empty">{{ t('system.logs.empty') }}</li>
      </ol>
    </section>

    <Dialog :open="clearOpen" :title="t('system.logs.clearTitle')" @close="clearOpen = false">
      <p class="logs__dialog-body">{{ t('system.logs.clearBody') }}</p>
      <template #footer>
        <Button variant="text" @click="clearOpen = false">{{ t('system.common.cancel') }}</Button>
        <Button
          :loading="clearBusy"
          :disabled="clearBusy"
          data-testid="syslog-clear-confirm"
          @click="confirmClear"
        >
          {{ t('system.logs.clear') }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.logs {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.logs__title {
  margin: 0;
  font: var(--gv-type-headline-medium);
  color: var(--gv-color-on-surface);
}

.logs__subtitle {
  margin: var(--gv-space-1) 0 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.logs__tabs {
  display: flex;
  gap: var(--gv-space-1);
  padding: var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container-low);
  align-self: flex-start;
}

.logs__tab {
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-4);
  border: none;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.logs__tab--active {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.logs__panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.logs__section-title {
  margin: var(--gv-space-2) 0 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.logs__tasks {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.logs__task {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
  min-height: var(--gv-size-topbar);
  padding: var(--gv-space-2) var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
}

.logs__task-main {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-3);
  flex-wrap: wrap;
}

.logs__task-name {
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface);
}

.logs__task-meta {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.logs__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.logs__autoscroll {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.logs__download {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.logs__meta {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.logs__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.logs__list {
  margin: 0;
  padding: var(--gv-space-2);
  list-style: none;
  max-height: 62vh;
  overflow: auto;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-lowest);
}

.logs__entry {
  display: grid;
  grid-template-columns: auto auto minmax(80px, 160px) minmax(0, 1fr);
  gap: var(--gv-space-2);
  padding: var(--gv-space-1) 0;
  border-bottom: 1px solid var(--gv-color-outline-variant);
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface);
}

.logs__level {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.logs__level[data-level="ERROR"],
.logs__level[data-level="CRITICAL"] {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.logs__level[data-level="WARNING"] {
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
}

.logs__time,
.logs__logger {
  color: var(--gv-color-on-surface-variant);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logs__message {
  overflow-wrap: anywhere;
}

.logs__context {
  grid-column: 4;
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

@media (max-width: 839px) {
  .logs {
    padding: var(--gv-space-3);
  }

  .logs__entry {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .logs__time,
  .logs__message,
  .logs__context {
    grid-column: 2;
  }
}
</style>
