<script setup lang="ts">
import type { IconName } from "@/components/icons/registry";
import Icon from "@/components/icons/Icon.vue";
import Button from "./Button.vue";

withDefaults(
  defineProps<{
    icon?: IconName;
    title?: string;
    body?: string;
    retryLabel?: string;
    testid?: string;
  }>(),
  {
    icon: "status-error",
    title: "",
    body: "",
    retryLabel: "",
    testid: "error-state",
  },
);

defineEmits<{ retry: [] }>();
</script>

<template>
  <div class="error-state" :data-testid="testid" role="alert">
    <div class="error-state__icon" aria-hidden="true">
      <Icon :name="icon" size="lg" />
    </div>
    <h2 v-if="title" class="error-state__title">{{ title }}</h2>
    <p v-if="body" class="error-state__body">{{ body }}</p>
    <Button
      v-if="retryLabel"
      class="error-state__retry"
      variant="outlined"
      :data-testid="`${testid}-retry`"
      @click="$emit('retry')"
    >
      {{ retryLabel }}
    </Button>
  </div>
</template>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--gv-space-1);
  padding: var(--gv-space-6);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
  color: var(--gv-color-on-surface);
  text-align: center;
}

.error-state__icon {
  color: var(--gv-color-error);
}

.error-state__icon :deep(.gv-icon) {
  width: var(--gv-space-7);
  height: var(--gv-space-7);
}

.error-state__title {
  margin: var(--gv-space-2) 0 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-error);
}

.error-state__body {
  max-width: 480px;
  margin: 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.error-state__retry {
  margin-top: var(--gv-space-4);
}
</style>
