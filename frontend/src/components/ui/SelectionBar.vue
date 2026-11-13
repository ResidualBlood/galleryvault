<script setup lang="ts">
import { useI18n } from "vue-i18n";
import Button from "./Button.vue";
import Icon from "@/components/icons/Icon.vue";
import { ensureLayoutMessages } from "./i18n/layout";

ensureLayoutMessages();

withDefaults(
  defineProps<{
    count: number;
    label?: string;
    clearLabel?: string;
    testid?: string;
  }>(),
  { label: "", clearLabel: "", testid: "gv-selection-bar" },
);

defineEmits<{ clear: [] }>();

const { t } = useI18n();
</script>

<template>
  <Transition name="selection">
    <div
      v-if="count > 0"
      class="selection"
      role="region"
      aria-live="polite"
      :data-testid="testid"
    >
      <span class="selection__count">{{ label || t("kit.selection.selected", { count }) }}</span>
      <div v-if="$slots.default" class="selection__actions">
        <slot />
      </div>
      <div v-if="$slots.danger" class="selection__danger">
        <slot name="danger" />
      </div>
      <Button
        class="selection__clear"
        variant="text"
        data-testid="gv-selection-clear"
        @click="$emit('clear')"
      >
        <Icon name="close" size="dense" />
        <span>{{ clearLabel || t("kit.selection.clear") }}</span>
      </Button>
    </div>
  </Transition>
</template>

<style scoped>
.selection {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-height: calc(var(--gv-size-control-lg) + var(--gv-space-4));
  padding: var(--gv-space-2) var(--gv-space-4);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.selection__count {
  font: var(--gv-type-label-large);
}

.selection__actions,
.selection__danger {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.selection__danger {
  margin-inline-start: auto;
}

.selection__clear {
  flex: none;
}

.selection-enter-active,
.selection-leave-active {
  transition:
    opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard),
    transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.selection-enter-from,
.selection-leave-to {
  opacity: 0;
  transform: translateY(calc(var(--gv-space-1) * -1));
}

@media (prefers-reduced-motion: reduce) {
  .selection-enter-active,
  .selection-leave-active {
    transition-duration: 1ms;
  }
}
</style>
