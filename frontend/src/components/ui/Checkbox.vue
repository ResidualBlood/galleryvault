<script setup lang="ts">
import { onMounted, ref, watchEffect } from "vue";
import Icon from "@/components/icons/Icon.vue";

/**
 * Checkbox replaces the native 13px checkbox used by pages: an 18px visual box
 * inside a 40px hit area, with a real (but visually hidden) native input so
 * keyboard, form and assistive semantics stay native.
 */
const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    /** Mixed state; the visual shows a dash and aria-checked becomes "mixed". */
    indeterminate?: boolean;
    label?: string;
    ariaLabel?: string;
    disabled?: boolean;
    id?: string;
  }>(),
  {
    modelValue: false,
    indeterminate: false,
    label: "",
    ariaLabel: "",
    disabled: false,
    id: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  change: [value: boolean];
}>();

const input = ref<HTMLInputElement | null>(null);

onMounted(() => {
  if (input.value) input.value.indeterminate = props.indeterminate;
});

watchEffect(() => {
  if (input.value) input.value.indeterminate = props.indeterminate;
});

function onChange(event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
  emit("update:modelValue", checked);
  emit("change", checked);
}
</script>

<template>
  <label
    class="checkbox"
    :class="{ 'checkbox--checked': modelValue, 'checkbox--mixed': indeterminate }"
  >
    <span class="checkbox__hit">
      <input
        :id="id || undefined"
        ref="input"
        class="checkbox__input"
        type="checkbox"
        :checked="modelValue"
        :disabled="disabled"
        :aria-label="!label && ariaLabel ? ariaLabel : undefined"
        :aria-checked="indeterminate ? 'mixed' : undefined"
        @change="onChange"
      />
      <span class="checkbox__box" aria-hidden="true">
        <Icon v-if="modelValue && !indeterminate" name="check" class="checkbox__mark" />
        <span v-else-if="indeterminate" class="checkbox__dash" />
      </span>
    </span>
    <span v-if="label || $slots.default" class="checkbox__label"><slot>{{ label }}</slot></span>
  </label>
</template>

<style scoped>
.checkbox {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-control-lg);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  cursor: pointer;
}

.checkbox__hit {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-control-lg);
  height: var(--gv-size-control-lg);
}

.checkbox__input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.checkbox__box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-icon-dense);
  height: var(--gv-size-icon-dense);
  border: var(--gv-state-focus-ring-width) solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: transparent;
  color: var(--gv-color-on-primary);
  transition:
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    border-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.checkbox__mark {
  width: calc(var(--gv-size-icon-dense) - var(--gv-space-1));
  height: calc(var(--gv-size-icon-dense) - var(--gv-space-1));
}

.checkbox__dash {
  width: var(--gv-space-2);
  height: var(--gv-state-focus-ring-width);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-on-primary);
}

.checkbox--checked .checkbox__box,
.checkbox--mixed .checkbox__box {
  border-color: var(--gv-color-primary);
  background: var(--gv-color-primary);
}

.checkbox__input:focus-visible + .checkbox__box {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.checkbox__input:disabled {
  cursor: not-allowed;
}

.checkbox__input:disabled + .checkbox__box {
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
  color: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-disabled), transparent);
}

.checkbox:has(.checkbox__input:disabled) {
  cursor: not-allowed;
  color: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-disabled), transparent);
}

@media (prefers-reduced-motion: reduce) {
  .checkbox__box {
    transition-duration: 1ms;
  }
}
</style>
