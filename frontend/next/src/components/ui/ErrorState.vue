<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    body?: string;
    retryLabel?: string;
    testid?: string;
  }>(),
  {
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
      <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor">
        <circle cx="12" cy="12" r="9" stroke-width="1.5" />
        <path d="M12 7.5v6" stroke-width="1.5" />
        <circle cx="12" cy="16.6" r="1" fill="currentColor" stroke="none" />
      </svg>
    </div>
    <h2 v-if="title" class="error-state__title">{{ title }}</h2>
    <p v-if="body" class="error-state__body">{{ body }}</p>
    <button v-if="retryLabel" class="error-state__retry" type="button" @click="$emit('retry')">
      {{ retryLabel }}
    </button>
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
  min-height: var(--gv-size-touch);
  margin-top: var(--gv-space-4);
  padding: 0 var(--gv-space-5);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  cursor: pointer;
}
</style>
