<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue?: string;
    id?: string;
    label?: string;
    placeholder?: string;
    error?: string;
    helper?: string;
    disabled?: boolean;
    required?: boolean;
    rows?: number;
    ariaLabel?: string;
  }>(),
  {
    modelValue: "",
    id: "",
    label: "",
    placeholder: "",
    error: "",
    helper: "",
    disabled: false,
    required: false,
    rows: 4,
    ariaLabel: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
}>();

const fieldId = props.id || `gv-textarea-${Math.random().toString(36).slice(2, 9)}`;

function onInput(event: Event): void {
  emit("update:modelValue", (event.target as HTMLTextAreaElement).value);
}

function onChange(event: Event): void {
  emit("change", (event.target as HTMLTextAreaElement).value);
}
</script>

<template>
  <label class="textarea-field" :class="{ 'textarea-field--error': Boolean(error) }" :for="fieldId">
    <span v-if="label" class="textarea-field__label">{{ label }}</span>
    <textarea
      :id="fieldId"
      data-gv-control
      class="textarea-field__control"
      :value="modelValue"
      :rows="rows"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :aria-label="!label && ariaLabel ? ariaLabel : undefined"
      :aria-invalid="Boolean(error) || undefined"
      :aria-describedby="error || helper ? `${fieldId}-help` : undefined"
      @input="onInput"
      @change="onChange"
    />
    <span
      v-if="error || helper"
      :id="`${fieldId}-help`"
      class="textarea-field__help"
      :role="error ? 'alert' : undefined"
    >
      {{ error || helper }}
    </span>
  </label>
</template>

<style scoped>
.textarea-field {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  width: 100%;
  min-width: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.textarea-field__control {
  width: 100%;
  min-height: calc(var(--gv-size-control-lg) * 2);
  padding: var(--gv-space-2) var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-large);
  resize: vertical;
  transition: border-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.textarea-field__control::placeholder {
  color: var(--gv-color-on-surface-variant);
}

.textarea-field__control:hover:not(:disabled) {
  border-color: var(--gv-color-on-surface-variant);
}

.textarea-field__control:focus {
  border-color: var(--gv-color-primary);
  border-width: var(--gv-state-focus-ring-width);
  padding: calc(var(--gv-space-2) - 1px) calc(var(--gv-space-4) - 1px);
}

.textarea-field--error .textarea-field__control {
  border-color: var(--gv-color-error);
}

.textarea-field--error .textarea-field__help {
  color: var(--gv-color-error);
}

.textarea-field__control:disabled {
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
