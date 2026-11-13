<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import {
  cancelArchive,
  fetchArchiveState,
  startArchive,
  type ArchiveState,
} from "@/api/archive";
import { purgeArchivedSources } from "@/api/system";
import { ApiError } from "@/api/client";
import { ensureSystemMessages } from "@/components/system/messages";

ensureSystemMessages();

const { t } = useI18n();
const state = ref<ArchiveState>({});
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const notice = ref("");
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
const statusLabel = computed(() => {
  if (running.value) return t("system.archive.running");
  if (failed.value > 0) return t("system.archive.failed");
  if (hasHistory.value) return t("system.archive.done");
  return t("system.archive.idle");
});

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function load(silent = false): Promise<void> {
  try {
    state.value = await fetchArchiveState();
    if (!silent) error.value = "";
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 401)) {
      error.value = cause instanceof Error ? cause.message : t("system.archive.loadFailed");
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
  error.value = "";
  try {
    const result = await startArchive();
    if (result.status === "paused") {
      error.value = result.detail ?? t("system.archive.startFailed");
    } else {
      notice.value = t("system.archive.started");
      state.value = { ...state.value, running: true };
      schedule();
    }
  } catch (cause) {
    error.value =
      cause instanceof ApiError && cause.status === 422
        ? t("system.archive.startFailed")
        : cause instanceof Error
          ? cause.message
          : String(cause);
  } finally {
    busy.value = false;
  }
}

async function cancel(): Promise<void> {
  busy.value = true;
  try {
    await cancelArchive();
    notice.value = t("system.archive.cancelled");
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}

async function purge(): Promise<void> {
  purgeBusy.value = true;
  try {
    await purgeArchivedSources();
    purgeOpen.value = false;
    notice.value = t("system.global.purgeStarted");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
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
  <div class="archive" data-testid="archive-page">
    <header class="archive__header">
      <h1 class="archive__title">{{ t('system.archive.title') }}</h1>
      <p class="archive__subtitle">{{ t('system.archive.subtitle') }}</p>
    </header>

    <div class="archive__toolbar">
      <Button
        :disabled="busy || running"
        :loading="busy"
        data-testid="archive-start"
        @click="start"
      >
        {{ t('system.archive.start') }}
      </Button>
      <Button
        variant="outlined"
        :disabled="busy || !running"
        data-testid="archive-cancel"
        @click="cancel"
      >
        {{ t('system.archive.cancel') }}
      </Button>
      <Button variant="outlined" data-testid="archive-purge" @click="purgeOpen = true">
        {{ t('system.archive.purge') }}
      </Button>
    </div>

    <p v-if="loading" class="archive__state">{{ t('system.common.loading') }}</p>
    <p v-if="error" class="archive__error" role="alert" data-testid="archive-error">{{ error }}</p>
    <p v-if="notice" class="archive__notice">{{ notice }}</p>

    <section class="archive__panel" data-testid="archive-status">
      <div class="archive__status-head">
        <span class="archive__status" :data-running="running">{{ statusLabel }}</span>
        <span class="archive__times">
          {{ t('system.archive.startedAt') }}: {{ formatTime(state.started_at) }} ·
          {{ t('system.archive.completedAt') }}: {{ formatTime(state.completed_at) }}
        </span>
      </div>

      <template v-if="hasHistory || running">
        <div class="archive__progress">
          <div class="archive__progress-bar" :style="{ width: `${percent}%` }" />
        </div>
        <p class="archive__progress-text">
          {{ t('system.archive.progress', { done: processed, total }) }} ({{ percent }}%)
        </p>
        <dl class="archive__stats">
          <div class="archive__stat">
            <dt>{{ t('system.archive.done') }}</dt>
            <dd>{{ done }}</dd>
          </div>
          <div class="archive__stat">
            <dt>{{ t('system.archive.skipped') }}</dt>
            <dd>{{ skipped }}</dd>
          </div>
          <div class="archive__stat">
            <dt>{{ t('system.archive.failed') }}</dt>
            <dd :data-failed="failed > 0">{{ failed }}</dd>
          </div>
          <div class="archive__stat">
            <dt>{{ t('system.archive.total') }}</dt>
            <dd>{{ total }}</dd>
          </div>
        </dl>
      </template>
      <p v-else class="archive__empty">{{ t('system.archive.empty') }}</p>

      <p v-if="state.last_error" class="archive__error">
        {{ t('system.archive.lastError') }}: {{ state.last_error }}
      </p>
    </section>

    <Dialog :open="purgeOpen" :title="t('system.archive.confirmPurgeTitle')" @close="purgeOpen = false">
      <p class="archive__dialog-body">{{ t('system.archive.confirmPurgeBody') }}</p>
      <template #footer>
        <Button variant="text" @click="purgeOpen = false">{{ t('system.common.cancel') }}</Button>
        <Button
          :loading="purgeBusy"
          :disabled="purgeBusy"
          data-testid="archive-purge-confirm"
          @click="purge"
        >
          {{ t('system.archive.purge') }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.archive {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  padding: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.archive__title {
  margin: 0;
  font: var(--gv-type-headline-medium);
  color: var(--gv-color-on-surface);
}

.archive__subtitle {
  margin: var(--gv-space-1) 0 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.archive__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.archive__state {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.archive__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.archive__notice {
  margin: 0;
  color: var(--gv-color-success);
  font: var(--gv-type-body-small);
}

.archive__panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.archive__status-head {
  display: flex;
  justify-content: space-between;
  gap: var(--gv-space-3);
  flex-wrap: wrap;
}

.archive__status {
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.archive__status[data-running="true"] {
  color: var(--gv-color-primary-text);
}

.archive__times {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.archive__progress {
  height: var(--gv-space-1);
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

.archive__progress-text {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.archive__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: var(--gv-space-2);
  margin: 0;
}

.archive__stat {
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-low);
}

.archive__stat dt {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.archive__stat dd {
  margin: var(--gv-space-1) 0 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.archive__stat dd[data-failed="true"] {
  color: var(--gv-color-error);
}

.archive__empty {
  margin: 0;
  padding: var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.archive__dialog-body {
  margin: 0;
  font: var(--gv-type-body-medium);
}

@media (max-width: 599px) {
  .archive {
    padding: var(--gv-space-3);
  }
}
</style>
