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
  align-items: center;
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
  opacity: var(--gv-state-disabled);
}

@media (prefers-reduced-motion: reduce) {
  .switch,
  .switch__thumb {
    transition-duration: 1ms;
  }
}
</style>
