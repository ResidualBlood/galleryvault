<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    label?: string;
    disabled?: boolean;
    id?: string;
  }>(),
  {
    label: "",
    disabled: false,
    id: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  change: [value: boolean];
}>();

function toggle(): void {
  emit("update:modelValue", !props.modelValue);
  emit("change", !props.modelValue);
}
</script>

<template>
  <button
    :id="id || undefined"
    type="button"
    role="switch"
    class="switch"
    :class="{ 'switch--on': modelValue }"
    :aria-checked="modelValue"
    :aria-label="label || undefined"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="switch__thumb" aria-hidden="true" />
  </button>
</template>

<style scoped>
.switch {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  align-self: center;
  width: 52px;
  height: 32px;
  padding: 4px;
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
  cursor: pointer;
  transition:
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    border-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.switch__thumb {
  width: 24px;
  height: 24px;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-outline);
  transition:
    transform var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.switch--on {
  border-color: var(--gv-color-primary);
  background: var(--gv-color-primary);
}

.switch--on .switch__thumb {
  background: var(--gv-color-on-primary);
  transform: translateX(20px);
}

.switch:disabled {
  cursor: not-allowed;
}

.switch:disabled .switch__thumb {
  background: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-disabled), transparent);
}

.switch:disabled:not(.switch--on) {
  border-color: color-mix(
    in srgb,
    var(--gv-color-on-surface) var(--gv-state-disabled-container),
    transparent
  );
  background: color-mix(
    in srgb,
    var(--gv-color-on-surface) var(--gv-state-disabled-container),
    transparent
  );
}

.switch:disabled.switch--on {
  border-color: color-mix(in srgb, var(--gv-color-primary) var(--gv-state-disabled), transparent);
  background: color-mix(in srgb, var(--gv-color-primary) var(--gv-state-disabled), transparent);
}

/* Explicit keyboard ring: the 52x32 track is the focusable element. */
.switch:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

@media (prefers-reduced-motion: reduce) {
  .switch,
  .switch__thumb {
    transition-duration: 1ms;
  }
}
</style>
