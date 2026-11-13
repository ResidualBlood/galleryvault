<script setup lang="ts">
import { computed, ref } from "vue";
import Icon from "@/components/icons/Icon.vue";
import { type IconName } from "@/components/icons/registry";
import {
  controlIconSize,
  useControlSize,
  type ControlSizeProp,
} from "@/components/ui/control-size";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    id?: string;
    label?: string;
    type?: string;
    placeholder?: string;
    autocomplete?: string;
    error?: string;
    helper?: string;
    disabled?: boolean;
    required?: boolean;
    /** Control ladder step; inherits from the surrounding toolbar by default. */
    size?: ControlSizeProp;
    /** Leading icon from the semantic registry. */
    icon?: IconName;
    /** Show a clear button while the field has a value. */
    clearable?: boolean;
    /** Accessible name for the clear button (callers translate it). */
    clearLabel?: string;
    /** Trailing unit slot ("px", "%", "s"). */
    unit?: string;
    /** Numeric bounds passed through to `<input type="number">`. */
    min?: number;
    max?: number;
    step?: number;
    /** Accessible name when no visual label is rendered. */
    ariaLabel?: string;
  }>(),
  {
    modelValue: "",
    id: "",
    label: "",
    type: "text",
    placeholder: "",
    autocomplete: "off",
    error: "",
    helper: "",
    disabled: false,
    required: false,
    size: "default",
    clearable: false,
    clearLabel: "Clear",
    unit: "",
    min: undefined,
    max: undefined,
    step: undefined,
    ariaLabel: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
  clear: [];
  enter: [];
}>();

const inputId = props.id || `gv-input-${Math.random().toString(36).slice(2, 9)}`;
const inputRef = ref<HTMLInputElement | null>(null);
const size = useControlSize(props.size);
const iconSize = computed(() => controlIconSize(size.value));
const showClear = computed(() => props.clearable && Boolean(props.modelValue) && !props.disabled);

function onInput(event: Event): void {
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}

function onChange(event: Event): void {
  emit("change", (event.target as HTMLInputElement).value);
}

function clear(): void {
  emit("update:modelValue", "");
  emit("change", "");
  emit("clear");
  inputRef.value?.focus();
}
</script>

<template>
  <label
    class="field"
    :class="[
      `field--${size}`,
      {
        'field--error': Boolean(error),
        'field--with-icon': Boolean(icon),
        'field--with-clear': showClear,
        'field--with-unit': Boolean(unit),
        'field--number': type === 'number',
      },
    ]"
    :for="inputId"
  >
    <span v-if="label" class="field__label">{{ label }}</span>
    <span class="field__box">
      <Icon v-if="icon" :name="icon" :size="iconSize" class="field__leading" />
      <input
        :id="inputId"
        ref="inputRef"
        data-gv-control
        class="field__control"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :autocomplete="autocomplete"
        :min="min"
        :max="max"
        :step="step"
        :disabled="disabled"
        :required="required"
        :aria-label="!label && ariaLabel ? ariaLabel : undefined"
        :aria-invalid="Boolean(error) || undefined"
        :aria-describedby="error || helper ? `${inputId}-help` : undefined"
        @input="onInput"
        @change="onChange"
        @keydown.enter.prevent="emit('enter')"
      />
      <span v-if="unit" class="field__unit" aria-hidden="true">{{ unit }}</span>
      <button
        v-if="showClear"
        type="button"
        class="field__clear"
        :aria-label="clearLabel"
        :title="clearLabel"
        @click.prevent.stop="clear"
      >
        <Icon name="close" size="sm" />
      </button>
    </span>
    <span
      v-if="error || helper"
      :id="`${inputId}-help`"
      class="field__help"
      :role="error ? 'alert' : undefined"
    >
      {{ error || helper }}
    </span>
  </label>
</template>

<style scoped>
.field {
  --gv-field-height: var(--gv-size-control-lg);
  --gv-field-padding: var(--gv-space-4);
  --gv-field-icon: var(--gv-size-icon-md);

  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  width: 100%;
  min-width: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.field--xl {
  --gv-field-height: var(--gv-size-control-xl);
}

.field--lg {
  --gv-field-height: var(--gv-size-control-lg);
}

.field--md {
  --gv-field-height: var(--gv-size-control-md);
}

.field--sm {
  --gv-field-height: var(--gv-size-control-sm);
  --gv-field-padding: var(--gv-space-3);
  --gv-field-icon: var(--gv-size-icon-dense);
}

.field__box {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
}

.field__control {
  width: 100%;
  min-width: 0;
  height: var(--gv-field-height);
  padding: 0 var(--gv-field-padding);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-large);
  transition: border-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.field__control::placeholder {
  color: var(--gv-color-on-surface-variant);
}

.field__control:hover:not(:disabled) {
  border-color: var(--gv-color-on-surface-variant);
}

.field__control:focus {
  border-color: var(--gv-color-primary);
  border-width: var(--gv-state-focus-ring-width);
  padding: 0 calc(var(--gv-field-padding) - 1px);
}

.field--with-icon .field__control {
  padding-left: calc(var(--gv-field-padding) + var(--gv-field-icon) + var(--gv-space-2));
}

.field--with-icon .field__control:focus {
  padding-left: calc(
    var(--gv-field-padding) + var(--gv-field-icon) + var(--gv-space-2) - 1px
  );
}

.field--with-clear .field__control,
.field--with-unit .field__control {
  padding-right: calc(var(--gv-field-padding) + var(--gv-size-control-sm));
}

.field__leading {
  position: absolute;
  left: var(--gv-field-padding);
  width: var(--gv-field-icon);
  height: var(--gv-field-icon);
  color: var(--gv-color-on-surface-variant);
  pointer-events: none;
}

.field__unit {
  position: absolute;
  right: var(--gv-field-padding);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  pointer-events: none;
}

.field__clear {
  position: absolute;
  top: 50%;
  right: var(--gv-space-1);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-control-sm);
  height: var(--gv-field-height);
  padding: 0;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  cursor: pointer;
  transform: translateY(-50%);
}

.field__clear:hover {
  color: var(--gv-color-primary-text);
}

.field__help {
  color: var(--gv-color-on-surface-variant);
}

.field--error .field__control {
  border-color: var(--gv-color-error);
}

.field--error .field__help {
  color: var(--gv-color-error);
}

.field__control:disabled {
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

.field--number .field__control {
  appearance: textfield;
  -moz-appearance: textfield;
  text-align: end;
}

.field--number .field__control::-webkit-outer-spin-button,
.field--number .field__control::-webkit-inner-spin-button {
  appearance: none;
  margin: 0;
}
</style>
