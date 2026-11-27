<script lang="ts">
export interface ChipProps {
  label: string;
  count?: number;
  icon?: import("@/components/icons/registry").IconName;
  selected?: boolean;
  variant?: "filter" | "assist";
  disabled?: boolean;
  testid?: string;
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/icons/Icon.vue";
import type { IconName } from "@/components/icons/registry";

const props = withDefaults(defineProps<ChipProps>(), {
  count: undefined,
  icon: undefined as IconName | undefined,
  selected: false,
  variant: "filter",
  disabled: false,
  testid: "gv-chip",
});

defineEmits<{ click: [event: MouseEvent] }>();

const countText = computed(() => {
  if (props.count === undefined) return "";
  return props.count > 99 ? "99+" : String(props.count);
});
</script>

<template>
  <button
    class="chip"
    :class="[
      `chip--${variant}`,
      { 'chip--selected': selected, 'chip--disabled': disabled },
    ]"
    type="button"
    :aria-pressed="variant === 'filter' ? selected : undefined"
    :disabled="disabled"
    :data-testid="testid"
    @click="$emit('click', $event)"
  >
    <Icon v-if="icon" :name="icon" size="dense" />
    <span class="chip__label">{{ label }}</span>
    <span v-if="countText" class="chip__count">{{ countText }}</span>
  </button>
</template>

<style scoped>
.chip {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-chip);
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.chip:hover:not(:disabled) {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.chip--assist {
  border-color: var(--gv-color-outline-variant);
  color: var(--gv-color-primary-text);
}

.chip--selected {
  border-color: transparent;
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.chip:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.chip--disabled {
  opacity: var(--gv-state-disabled);
  cursor: not-allowed;
}

.chip__label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.chip__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--gv-size-icon-sm);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, currentColor 14%, transparent);
  font: var(--gv-type-label-small);
}
</style>
