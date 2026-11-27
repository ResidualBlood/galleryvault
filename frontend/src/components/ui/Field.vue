<script setup lang="ts">
/**
 * Field wraps one control with a label and helper / error text in the two
 * layouts the app needs: label above (forms, dialogs) and label inline
 * (settings rows). Toolbar inputs stay label-free and use placeholder +
 * aria-label instead.
 */
withDefaults(
  defineProps<{
    label?: string;
    helper?: string;
    error?: string;
    layout?: "above" | "inline";
    /** id of the wrapped control, for the label's `for` attribute. */
    labelFor?: string;
    required?: boolean;
  }>(),
  {
    label: "",
    helper: "",
    error: "",
    layout: "above",
    labelFor: "",
    required: false,
  },
);
</script>

<template>
  <div
    class="gv-field"
    :class="[`gv-field--${layout}`, { 'gv-field--error': Boolean(error) }]"
  >
    <label v-if="label" class="gv-field__label" :for="labelFor || undefined">
      {{ label }}
      <span v-if="required" class="gv-field__required" aria-hidden="true">*</span>
    </label>
    <div class="gv-field__body">
      <slot />
      <span v-if="error || helper" class="gv-field__help" :role="error ? 'alert' : undefined">
        {{ error || helper }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.gv-field {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.gv-field--inline {
  display: grid;
  grid-template-columns: minmax(120px, 220px) minmax(0, 1fr);
  align-items: center;
  gap: var(--gv-space-4);
}

.gv-field__label {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}

.gv-field--inline .gv-field__label {
  color: var(--gv-color-on-surface-variant);
}

.gv-field__required {
  color: var(--gv-color-error);
}

.gv-field__body {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.gv-field__help {
  color: var(--gv-color-on-surface-variant);
}

.gv-field--error .gv-field__help {
  color: var(--gv-color-error);
}

@media (max-width: 599.98px) {
  .gv-field--inline {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--gv-space-1);
  }
}
</style>
