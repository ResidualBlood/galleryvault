<script setup lang="ts">
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
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
  enter: [];
}>();

const inputId = props.id || `gv-input-${Math.random().toString(36).slice(2, 9)}`;

function onInput(event: Event): void {
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}

function onChange(event: Event): void {
  emit("change", (event.target as HTMLInputElement).value);
}
</script>

<template>
  <label class="field" :class="{ 'field--error': Boolean(error) }" :for="inputId">
    <span v-if="label" class="field__label">{{ label }}</span>
    <input
      :id="inputId"
      class="field__control"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      :disabled="disabled"
      :required="required"
      :aria-invalid="Boolean(error) || undefined"
      :aria-describedby="error || helper ? `${inputId}-help` : undefined"
      @input="onInput"
      @change="onChange"
      @keydown.enter.prevent="emit('enter')"
    />
    <span v-if="error || helper" :id="`${inputId}-help`" class="field__help">
      {{ error || helper }}
    </span>
  </label>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.field__control {
  height: 48px;
  padding: 0 var(--gv-space-3);
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

.field__control:hover {
  border-color: var(--gv-color-on-surface-variant);
}

.field__control:focus {
  outline: none;
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 1px var(--gv-color-primary);
}

.field--error .field__control {
  border-color: var(--gv-color-error);
}

.field--error .field__help {
  color: var(--gv-color-error);
}

.field__control:disabled {
  cursor: not-allowed;
  opacity: var(--gv-state-disabled);
}
</style>
