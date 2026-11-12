<script setup lang="ts">
export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

withDefaults(
  defineProps<{
    modelValue: string;
    options: SelectOption[];
    id?: string;
    label?: string;
    disabled?: boolean;
    error?: string;
    helper?: string;
  }>(),
  {
    id: "",
    label: "",
    disabled: false,
    error: "",
    helper: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
}>();

function onChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  emit("update:modelValue", value);
  emit("change", value);
}
</script>

<template>
  <label class="select-field" :class="{ 'select-field--error': Boolean(error) }">
    <span v-if="label" class="select-field__label">{{ label }}</span>
    <span class="select-field__wrap">
      <select
        :id="id || undefined"
        class="select-field__control"
        :value="modelValue"
        :disabled="disabled"
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
      <span class="select-field__chevron" aria-hidden="true">▾</span>
    </span>
    <span v-if="error || helper" class="select-field__help">{{ error || helper }}</span>
  </label>
</template>

<style scoped>
.select-field {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.select-field__wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.select-field__control {
  width: 100%;
  height: 48px;
  padding: 0 var(--gv-space-7) 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-large);
  appearance: none;
}

.select-field__control:focus {
  outline: none;
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 1px var(--gv-color-primary);
}

.select-field__chevron {
  position: absolute;
  right: var(--gv-space-3);
  pointer-events: none;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.select-field--error .select-field__control {
  border-color: var(--gv-color-error);
}

.select-field--error .select-field__help {
  color: var(--gv-color-error);
}

.select-field__control:disabled {
  cursor: not-allowed;
  opacity: var(--gv-state-disabled);
}
</style>
