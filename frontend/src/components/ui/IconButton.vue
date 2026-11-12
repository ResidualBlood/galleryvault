<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string;
    disabled?: boolean;
    selected?: boolean;
    size?: "default" | "small";
    type?: "button" | "submit";
  }>(),
  {
    disabled: false,
    selected: false,
    size: "default",
    type: "button",
  },
);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    :aria-label="label"
    :aria-pressed="selected || undefined"
    class="icon-btn"
    :class="{ 'icon-btn--small': size === 'small', 'icon-btn--selected': selected }"
  >
    <span class="icon-btn__surface">
      <slot />
    </span>
  </button>
</template>

<style scoped>
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  padding: 0;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  cursor: pointer;
}

.icon-btn__surface {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--gv-radius-full);
  transition: background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.icon-btn:hover .icon-btn__surface {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.icon-btn:active .icon-btn__surface {
  background: color-mix(in srgb, currentColor 12%, transparent);
}

.icon-btn--selected .icon-btn__surface {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.icon-btn--small {
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
}

.icon-btn--small .icon-btn__surface {
  width: 32px;
  height: 32px;
}

.icon-btn:disabled {
  cursor: not-allowed;
  opacity: var(--gv-state-disabled);
}
</style>
