<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import {
  createApiToken,
  fetchApiTokenStatus,
  revokeApiToken,
  type ApiTokenStatus,
} from "@/api/settings";
import { ApiError } from "@/api/client";

const { t } = useI18n();
const status = ref<ApiTokenStatus>({ configured: false });
const token = ref("");
const busy = ref(false);
const error = ref("");
const copied = ref(false);
const revokeOpen = ref(false);

const statusText = computed(() => {
  if (!status.value.configured) return t("settings.token.statusMissing");
  const created = status.value.created_at;
  if (!created) return t("settings.token.statusConfigured", { date: "—" });
  let date = created;
  try {
    date = new Date(created).toLocaleString();
  } catch {
    /* keep the raw ISO string */
  }
  return t("settings.token.statusConfigured", { date });
});

async function refresh(): Promise<void> {
  try {
    status.value = await fetchApiTokenStatus();
  } catch {
    /* status is best-effort; generation still works */
  }
}

onMounted(refresh);

async function generate(): Promise<void> {
  error.value = "";
  busy.value = true;
  try {
    const result = await createApiToken();
    token.value = result.token;
    copied.value = false;
    await refresh();
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(token.value);
    copied.value = true;
  } catch {
    copied.value = false;
  }
}

function hide(): void {
  token.value = "";
  copied.value = false;
}

async function revoke(): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    await revokeApiToken();
    token.value = "";
    status.value = { configured: false };
    revokeOpen.value = false;
    await refresh();
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="panel" data-settings-section="api-token">
    <div class="panel__head">
      <h3 class="panel__title">{{ t('settings.token.title') }}</h3>
      <span class="panel__status" data-testid="api-token-status">{{ statusText }}</span>
    </div>
    <p class="panel__body">{{ t('settings.token.description') }}</p>

    <div v-if="token" class="token" data-testid="api-token-once">
      <p class="token__warning">{{ t('settings.token.once') }}</p>
      <code class="token__value" data-testid="api-token-plaintext">{{ token }}</code>
      <div class="token__actions">
        <Button variant="tonal" size="compact" @click="copy">
          {{ copied ? t('settings.token.copied') : t('settings.token.copy') }}
        </Button>
        <Button variant="text" size="compact" @click="hide">
          {{ t('settings.token.hide') }}
        </Button>
      </div>
    </div>

    <p v-if="error" class="panel__error" role="alert">{{ error }}</p>

    <div class="panel__actions">
      <Button :disabled="busy" :loading="busy" data-testid="api-token-generate" @click="generate">
        {{ status.configured ? t('settings.token.regenerate') : t('settings.token.generate') }}
      </Button>
      <Button
        v-if="status.configured"
        variant="outlined"
        :disabled="busy"
        data-testid="api-token-revoke"
        @click="revokeOpen = true"
      >
        {{ t('settings.token.revoke') }}
      </Button>
    </div>

    <Dialog :open="revokeOpen" :title="t('settings.token.revokeConfirmTitle')" @close="revokeOpen = false">
      <p class="panel__body">{{ t('settings.token.revokeConfirmBody') }}</p>
      <template #footer>
        <Button variant="text" @click="revokeOpen = false">
          {{ t('settings.security.cancel') }}
        </Button>
        <Button variant="filled" :disabled="busy" :loading="busy" data-testid="api-token-revoke-confirm" @click="revoke">
          {{ t('settings.token.revoke') }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.panel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-3);
  flex-wrap: wrap;
}

.panel__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.panel__status {
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.panel__body {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.panel__error {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-error);
}

.panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.token {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-warning);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
}

.token__warning {
  margin: 0;
  font: var(--gv-type-body-small);
}

.token__value {
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  overflow-wrap: anywhere;
}

.token__actions {
  display: flex;
  gap: var(--gv-space-2);
}
</style>
