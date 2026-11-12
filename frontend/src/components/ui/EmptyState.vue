<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    body?: string;
    actionLabel?: string;
    secondaryLabel?: string;
    testid?: string;
  }>(),
  {
    title: "",
    body: "",
    actionLabel: "",
    secondaryLabel: "",
    testid: "empty-state",
  },
);

defineEmits<{ action: []; secondary: [] }>();
</script>

<template>
  <div class="state" :data-testid="testid">
    <div class="state__icon" aria-hidden="true">
      <slot name="icon">
        <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor">
          <rect x="3.5" y="4.5" width="17" height="15" rx="2" stroke-width="1.5" />
          <path d="M3.5 16l5-5 4 4 3-3 5 5" stroke-width="1.5" />
        </svg>
      </slot>
    </div>
    <h2 v-if="title" class="state__title">{{ title }}</h2>
    <p v-if="body" class="state__body">{{ body }}</p>
    <div v-if="actionLabel || secondaryLabel || $slots.default" class="state__actions">
      <slot />
      <button v-if="actionLabel" class="state__primary" type="button" @click="$emit('action')">
        {{ actionLabel }}
      </button>
      <button
        v-if="secondaryLabel"
        class="state__secondary"
        type="button"
        @click="$emit('secondary')"
      >
        {{ secondaryLabel }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-1);
  padding: var(--gv-space-6);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
  color: var(--gv-color-on-surface);
  text-align: center;
}

.state__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-7);
  height: var(--gv-space-7);
  color: var(--gv-color-on-surface-variant);
}

.state__title {
  margin: var(--gv-space-2) 0 0;
  font: var(--gv-type-title-medium);
}

.state__body {
  max-width: 480px;
  margin: 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.state__actions {
  display: flex;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-4);
}

.state__primary,
.state__secondary {
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-5);
  border-radius: var(--gv-radius-full);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.state__primary {
  border: 1px solid var(--gv-color-primary);
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
}

.state__secondary {
  border: 1px solid var(--gv-color-outline);
  background: transparent;
  color: var(--gv-color-primary-text);
}

@media (min-width: 840px) {
  .state {
    padding: var(--gv-space-7);
  }
}
</style>
