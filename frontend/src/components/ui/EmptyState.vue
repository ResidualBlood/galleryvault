<script setup lang="ts">
import type { IconName } from "@/components/icons/registry";
import Icon from "@/components/icons/Icon.vue";
import Button from "./Button.vue";

withDefaults(
  defineProps<{
    icon?: IconName;
    title?: string;
    body?: string;
    actionLabel?: string;
    secondaryLabel?: string;
    testid?: string;
  }>(),
  {
    icon: "browse",
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
        <Icon :name="icon" size="lg" />
      </slot>
    </div>
    <h2 v-if="title" class="state__title">{{ title }}</h2>
    <p v-if="body" class="state__body">{{ body }}</p>
    <div v-if="actionLabel || secondaryLabel || $slots.default" class="state__actions">
      <slot />
      <Button
        v-if="actionLabel"
        variant="filled"
        :data-testid="`${testid}-action`"
        @click="$emit('action')"
      >
        {{ actionLabel }}
      </Button>
      <Button
        v-if="secondaryLabel"
        variant="outlined"
        :data-testid="`${testid}-secondary`"
        @click="$emit('secondary')"
      >
        {{ secondaryLabel }}
      </Button>
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
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface);
  text-align: center;
}

.state__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gv-color-on-surface-variant);
}

.state__icon :deep(.gv-icon) {
  width: var(--gv-space-7);
  height: var(--gv-space-7);
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
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-4);
}

@media (min-width: 840px) {
  .state {
    padding: var(--gv-space-7);
  }
}
</style>
