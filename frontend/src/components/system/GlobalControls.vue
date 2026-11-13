<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import {
  fetchPause,
  fetchScanStatus,
  purgeArchivedSources,
  setPaused,
  triggerScan,
  type ScanState,
} from "@/api/system";
import { ApiError } from "@/api/client";
import "./messages";

const { t } = useI18n();
const paused = ref(false);
const scan = ref<ScanState>({});
const busy = ref(false);
const error = ref("");
const purgeOpen = ref(false);
const purgeBusy = ref(false);
let timer: number | null = null;

const scanning = computed(() => Boolean(scan.value.running));

async function load(silent = false): Promise<void> {
  try {
    const [pause, scanState] = await Promise.all([fetchPause(), fetchScanStatus()]);
    paused.value = pause.paused;
    scan.value = scanState;
    if (!silent) error.value = "";
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 401)) {
      error.value = cause instanceof Error ? cause.message : t("system.global.loadFailed");
    }
  }
  schedule();
}

function schedule(): void {
  if (timer !== null) {
    window.clearTimeout(timer);
    timer = null;
  }
  if (scanning.value) timer = window.setTimeout(() => void load(true), 3000);
}

async function togglePause(): Promise<void> {
  busy.value = true;
  try {
    paused.value = (await setPaused(!paused.value)).paused;
    error.value = "";
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t("system.global.pauseFailed");
  } finally {
    busy.value = false;
  }
}

async function scanNow(): Promise<void> {
  busy.value = true;
  try {
    await triggerScan();
    scan.value = { ...scan.value, running: true };
    schedule();
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
  <section class="global" data-testid="global-controls">
    <div class="global__row">
      <Button
        :variant="paused ? 'tonal' : 'outlined'"
        :disabled="busy"
        :data-testid="paused ? 'global-resume' : 'global-pause'"
        @click="togglePause"
      >
        {{ paused ? t('system.global.resume') : t('system.global.pause') }}
      </Button>
      <Button
        variant="filled"
        :disabled="busy || scanning"
        :loading="scanning"
        data-testid="global-scan"
        @click="scanNow"
      >
        {{ scanning ? t('system.global.scanning') : t('system.global.scan') }}
      </Button>
      <Button variant="outlined" data-testid="global-purge" @click="purgeOpen = true">
        {{ t('system.global.purge') }}
      </Button>
      <span v-if="paused" class="global__status" data-testid="global-paused">{{ t('system.global.paused') }}</span>
    </div>
    <p v-if="error" class="global__error" role="alert">{{ error }}</p>

    <Dialog :open="purgeOpen" :title="t('system.global.purgeTitle')" @close="purgeOpen = false">
      <p class="global__body">{{ t('system.global.purgeBody') }}</p>
      <template #footer>
        <Button variant="text" @click="purgeOpen = false">{{ t('system.global.cookie.dismiss') }}</Button>
        <Button
          variant="filled"
          :loading="purgeBusy"
          :disabled="purgeBusy"
          data-testid="global-purge-confirm"
          @click="purge"
        >
          {{ t('system.global.purge') }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.global {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-low);
}

.global__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.global__status {
  color: var(--gv-color-warning);
  font: var(--gv-type-label-large);
}

.global__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.global__body {
  margin: 0;
  font: var(--gv-type-body-medium);
}
</style>
