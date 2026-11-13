<!-- gv-polish:pending -->
<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { changePassword } from "@/api/auth";
import { ApiError } from "@/api/client";

const emit = defineEmits<{ changed: [] }>();
const { t } = useI18n();

const current = ref("");
const next = ref("");
const confirm = ref("");
const busy = ref(false);
const error = ref("");

async function submit(): Promise<void> {
  error.value = "";
  if (!current.value || !next.value) {
    error.value = t("settings.password.required");
    return;
  }
  if (next.value !== confirm.value) {
    error.value = t("settings.password.mismatch");
    return;
  }
  busy.value = true;
  try {
    await changePassword(current.value, next.value);
    current.value = "";
    next.value = "";
    confirm.value = "";
    emit("changed");
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="panel" data-settings-section="password">
    <h3 class="panel__title">{{ t('settings.password.title') }}</h3>
    <div class="panel__grid">
      <Input
        v-model="current"
        type="password"
        autocomplete="current-password"
        :label="t('settings.password.current')"
      />
      <Input
        v-model="next"
        type="password"
        autocomplete="new-password"
        :label="t('settings.password.next')"
      />
      <Input
        v-model="confirm"
        type="password"
        autocomplete="new-password"
        :label="t('settings.password.confirm')"
      />
    </div>
    <p v-if="error" class="panel__error" role="alert">{{ error }}</p>
    <div class="panel__actions">
      <Button :disabled="busy" :loading="busy" @click="submit">
        {{ t('settings.password.submit') }}
      </Button>
    </div>
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

.panel__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.panel__grid {
  display: grid;
  gap: var(--gv-space-3);
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}

.panel__error {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-error);
}

.panel__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
