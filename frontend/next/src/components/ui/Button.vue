<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "filled" | "tonal" | "outlined" | "text";
    size?: "default" | "compact";
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
    loading?: boolean;
  }>(),
  {
    variant: "filled",
    size: "default",
    type: "button",
    disabled: false,
    loading: false,
  },
);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="btn"
    :class="[`btn--${variant}`, `btn--${size}`]"
  >
    <span v-if="loading" class="btn__spinner" aria-hidden="true" />
    <slot />
  </button>
</template>

<style scoped>
.btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  height: 40px;
  padding: 0 var(--gv-space-4);
  border: 1px solid transparent;
  border-radius: var(--gv-radius-full);
  font: var(--gv-type-label-large);
  cursor: pointer;
  overflow: hidden;
  transition:
    box-shadow var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.btn::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: currentColor;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.btn:hover::after {
  opacity: var(--gv-state-hover);
}

.btn:active::after {
  opacity: var(--gv-state-pressed);
}

.btn:disabled {
  cursor: not-allowed;
  opacity: var(--gv-state-disabled);
}

.btn--compact {
  height: 32px;
  padding: 0 var(--gv-space-3);
}

.btn--filled {
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
}

.btn--tonal {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.btn--outlined {
  background: transparent;
  border-color: var(--gv-color-outline);
  color: var(--gv-color-primary-text);
}

.btn--text {
  background: transparent;
  color: var(--gv-color-primary-text);
  padding: 0 var(--gv-space-3);
}

.btn__spinner {
  width: var(--gv-size-icon-sm);
  height: var(--gv-size-icon-sm);
  border: var(--gv-state-focus-ring-width) solid currentColor;
  border-right-color: transparent;
  border-radius: var(--gv-radius-full);
  animation: btn-spin 700ms linear infinite;
}

@keyframes btn-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn,
  .btn::after {
    transition-duration: 1ms;
  }

  .btn__spinner {
    animation-duration: 2s;
  }
}
</style>
