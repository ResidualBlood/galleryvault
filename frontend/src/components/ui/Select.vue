<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/icons/Icon.vue";
import {
  controlIconSize,
  useControlSize,
  type ControlSizeProp,
} from "@/components/ui/control-size";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

const props = withDefaults(
  defineProps<{
    modelValue: string;
    options: SelectOption[];
    id?: string;
    label?: string;
    disabled?: boolean;
    error?: string;
    helper?: string;
    /** Control ladder step; inherits from the surrounding toolbar by default. */
    size?: ControlSizeProp;
    /** Accessible name when no visual label is rendered. */
    ariaLabel?: string;
  }>(),
  {
    id: "",
    label: "",
    disabled: false,
    error: "",
    helper: "",
    size: "default",
    ariaLabel: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
}>();

const size = useControlSize(props.size);
const iconSize = computed(() => controlIconSize(size.value));

function onChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  emit("update:modelValue", value);
  emit("change", value);
}
</script>

<template>
  <label
    class="select-field"
    :class="[`select-field--${size}`, { 'select-field--error': Boolean(error) }]"
  >
    <span v-if="label" class="select-field__label">{{ label }}</span>
    <span class="select-field__wrap">
      <select
        :id="id || undefined"
        data-gv-control
        class="select-field__control"
        :value="modelValue"
        :disabled="disabled"
        :aria-label="!label && ariaLabel ? ariaLabel : undefined"
        :aria-invalid="Boolean(error) || undefined"
        @change="onChange"
      >
        <option
          v-for="option in options"
          :key="option.value"
          :value="option.value"
          :disabled="option.disabled"
        >
          {{ option.label }}
        </option>
      </select>
      <Icon
        name="chevron-down"
        :size="iconSize"
        class="select-field__chevron"
        aria-hidden="true"
      />
    </span>
    <span v-if="error || helper" class="select-field__help">{{ error || helper }}</span>
  </label>
</template>

<style scoped>
.select-field {
  --gv-select-height: var(--gv-size-control-lg);
  --gv-select-padding: var(--gv-space-4);
  --gv-select-icon: var(--gv-size-icon-md);

  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  width: 100%;
  min-width: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.select-field--xl {
  --gv-select-height: var(--gv-size-control-xl);
}

.select-field--lg {
  --gv-select-height: var(--gv-size-control-lg);
}

.select-field--md {
  --gv-select-height: var(--gv-size-control-md);
}

.select-field--sm {
  --gv-select-height: var(--gv-size-control-sm);
  --gv-select-padding: var(--gv-space-3);
  --gv-select-icon: var(--gv-size-icon-dense);
}

.select-field__wrap {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
}

.select-field__control {
  width: 100%;
  min-width: 0;
  height: var(--gv-select-height);
  padding: 0 calc(var(--gv-select-padding) + var(--gv-select-icon) + var(--gv-space-2)) 0
    var(--gv-select-padding);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-large);
  appearance: none;
  text-overflow: ellipsis;
  transition: border-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.select-field__control:hover:not(:disabled) {
  border-color: var(--gv-color-on-surface-variant);
}

.select-field__control:focus {
  border-color: var(--gv-color-primary);
  border-width: var(--gv-state-focus-ring-width);
  padding-left: calc(var(--gv-select-padding) - 1px);
}

.select-field__chevron {
  position: absolute;
  right: var(--gv-select-padding);
  top: 50%;
  width: var(--gv-select-icon);
  height: var(--gv-select-icon);
  color: var(--gv-color-on-surface-variant);
  pointer-events: none;
  transform: translateY(-50%);
}

.select-field--error .select-field__control {
  border-color: var(--gv-color-error);
}

.select-field--error .select-field__help {
  color: var(--gv-color-error);
}

.select-field__control:disabled {
  cursor: not-allowed;
  border-color: color-mix(
    in srgb,
    var(--gv-color-on-surface) var(--gv-state-disabled-container),
    transparent
  );
  background: color-mix(
    in srgb,
    var(--gv-color-on-surface) var(--gv-state-disabled-container),
    var(--gv-color-surface-container-lowest)
  );
  color: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-disabled), transparent);
}
</style>
