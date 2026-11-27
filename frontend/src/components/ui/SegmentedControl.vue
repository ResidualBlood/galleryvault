<script lang="ts">
export interface SegmentedOption {
  value: string;
  label: string;
  icon?: import("@/components/icons/registry").IconName;
  disabled?: boolean;
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/icons/Icon.vue";
import { useControlSize, type ControlSizeProp } from "@/components/ui/control-size";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    options: SegmentedOption[];
    label: string;
    disabled?: boolean;
    testid?: string;
    /** Control ladder step; the outer frame is exactly that step (40/36/32). */
    size?: ControlSizeProp;
  }>(),
  { disabled: false, testid: "gv-segmented", size: "default" },
);

const size = useControlSize(props.size);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
}>();

const enabled = computed(() => props.options.filter((option) => !option.disabled));

function activate(option: SegmentedOption, focusTarget?: HTMLElement): void {
  if (props.disabled || option.disabled || option.value === props.modelValue) return;
  emit("update:modelValue", option.value);
  emit("change", option.value);
  focusTarget?.focus();
}

function onKeydown(event: KeyboardEvent): void {
  if (props.disabled) return;
  const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];
  if (!keys.includes(event.key)) return;
  const target = event.target as HTMLElement;
  const value = target.dataset.segmentedValue;
  const buttons = [
    ...((event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>(
      '[role="radio"]:not(:disabled)',
    ) ?? []),
  ];
  const current = buttons.findIndex((button) => button.dataset.segmentedValue === value);
  if (current < 0) return;
  event.preventDefault();
  let next = current;
  if (event.key === "Home") next = 0;
  else if (event.key === "End") next = buttons.length - 1;
  else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    next = current <= 0 ? buttons.length - 1 : current - 1;
  } else {
    next = current >= buttons.length - 1 ? 0 : current + 1;
  }
  activate(enabled.value[next], buttons[next]);
}
</script>

<template>
  <div
    class="segmented"
    :class="[`segmented--${size}`, { 'segmented--disabled': disabled }]"
    role="radiogroup"
    :aria-label="label"
    :aria-disabled="disabled || undefined"
    :data-testid="testid"
    @keydown="onKeydown"
  >
    <button
      v-for="option in options"
      :key="option.value"
      class="segmented__item"
      :class="{ 'segmented__item--selected': option.value === modelValue }"
      type="button"
      role="radio"
      :aria-checked="option.value === modelValue"
      :disabled="disabled || option.disabled"
      :tabindex="option.value === modelValue ? 0 : -1"
      :data-segmented-value="option.value"
      @click="activate(option)"
    >
      <Icon v-if="option.icon" :name="option.icon" size="dense" />
      <span class="segmented__label">{{ option.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.segmented {
  --segmented-height: var(--gv-size-control-lg);

  display: inline-grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  gap: 2px;
  height: var(--segmented-height);
  padding: 1px;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container-low);
}

.segmented--xl {
  --segmented-height: var(--gv-size-control-xl);
}

.segmented--lg {
  --segmented-height: var(--gv-size-control-lg);
}

.segmented--md {
  --segmented-height: var(--gv-size-control-md);
}

.segmented--sm {
  --segmented-height: var(--gv-size-control-sm);
}

.segmented--disabled {
  opacity: var(--gv-state-disabled);
}

.segmented__item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-1);
  min-width: 0;
  height: calc(var(--segmented-height) - 4px);
  padding: 0 var(--gv-space-3);
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  white-space: nowrap;
  cursor: pointer;
  transition: background-color var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.segmented__item:hover:not(:disabled):not(.segmented__item--selected) {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.segmented__item--selected {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.segmented__item:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.segmented__item:disabled {
  cursor: not-allowed;
}

.segmented__label {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
