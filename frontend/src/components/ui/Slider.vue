<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: number;
    min?: number;
    max?: number;
    step?: number;
    disabled?: boolean;
    label?: string;
    id?: string;
    ariaLabel?: string;
    /** Render the current value next to the track. */
    showValue?: boolean;
  }>(),
  {
    min: 0,
    max: 100,
    step: 1,
    disabled: false,
    label: "",
    id: "",
    ariaLabel: "",
    showValue: false,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: number];
  change: [value: number];
}>();

const sliderId = props.id || `gv-slider-${Math.random().toString(36).slice(2, 9)}`;

function onInput(event: Event): void {
  emit("update:modelValue", Number((event.target as HTMLInputElement).value));
}

function onChange(event: Event): void {
  emit("change", Number((event.target as HTMLInputElement).value));
}
</script>

<template>
  <label class="slider" :for="sliderId">
    <span v-if="label || showValue" class="slider__header">
      <span v-if="label" class="slider__label">{{ label }}</span>
      <span v-if="showValue" class="slider__value">{{ modelValue }}</span>
    </span>
    <input
      :id="sliderId"
      data-gv-control
      class="slider__input"
      type="range"
      :value="modelValue"
      :min="min"
      :max="max"
      :step="step"
      :disabled="disabled"
      :aria-label="!label && ariaLabel ? ariaLabel : undefined"
      @input="onInput"
      @change="onChange"
    />
  </label>
</template>

<style scoped>
.slider {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  width: 100%;
  min-width: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.slider__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.slider__label {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}

.slider__value {
  font: var(--gv-type-label-large);
  font-variant-numeric: tabular-nums;
}

.slider__input {
  width: 100%;
  height: var(--gv-size-touch);
  margin: 0;
  padding: 0;
  background: transparent;
  appearance: none;
  cursor: pointer;
}

.slider__input:disabled {
  cursor: not-allowed;
}

.slider__input:focus {
  outline: none;
}

.slider__input:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
  border-radius: var(--gv-radius-full);
}

.slider__input::-webkit-slider-runnable-track {
  height: var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.slider__input::-webkit-slider-thumb {
  width: var(--gv-size-icon-md);
  height: var(--gv-size-icon-md);
  margin-top: calc((var(--gv-space-1) - var(--gv-size-icon-md)) / 2);
  border: 0;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  appearance: none;
}

.slider__input::-moz-range-track {
  height: var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.slider__input::-moz-range-thumb {
  width: var(--gv-size-icon-md);
  height: var(--gv-size-icon-md);
  border: 0;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.slider__input:disabled::-webkit-slider-thumb {
  background: color-mix(in srgb, var(--gv-color-primary) var(--gv-state-disabled), transparent);
}

.slider__input:disabled::-moz-range-thumb {
  background: color-mix(in srgb, var(--gv-color-primary) var(--gv-state-disabled), transparent);
}
</style>
