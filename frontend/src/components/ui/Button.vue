<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/icons/Icon.vue";
import { type IconName } from "@/components/icons/registry";
import {
  controlIconSize,
  useControlSize,
  type ControlSizeProp,
} from "@/components/ui/control-size";

const props = withDefaults(
  defineProps<{
    variant?: "filled" | "tonal" | "outlined" | "text";
    /**
     * `lg` / `md` / `sm` are the control ladder; `xl` is for the login and
     * welcome single-column forms. `default` inherits the surrounding step and
     * `compact` is the legacy alias for `sm`.
     */
    size?: ControlSizeProp;
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
    loading?: boolean;
    /** Leading icon, rendered from the semantic registry. */
    icon?: IconName;
    /** Trailing icon, rendered from the semantic registry. */
    iconEnd?: IconName;
    /** Destructive action: error colour on outlined / text, error container otherwise. */
    danger?: boolean;
  }>(),
  {
    variant: "filled",
    size: "default",
    type: "button",
    disabled: false,
    loading: false,
    danger: false,
  },
);

const size = useControlSize(props.size);
const iconSize = computed(() => controlIconSize(size.value));
</script>

<template>
  <button
    :type="type"
    data-gv-control
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="btn"
    :class="[
      `btn--${variant}`,
      `btn--${size}`,
      { 'btn--danger': danger, 'btn--loading': loading },
    ]"
  >
    <span v-if="loading" class="btn__spinner" aria-hidden="true" />
    <Icon v-else-if="icon" :name="icon" :size="iconSize" class="btn__icon" />
    <slot name="leading" />
    <slot />
    <slot name="trailing" />
    <Icon v-if="iconEnd && !loading" :name="iconEnd" :size="iconSize" class="btn__icon" />
  </button>
</template>

<style scoped>
.btn {
  --gv-btn-height: var(--gv-size-control-lg);
  --gv-btn-padding: var(--gv-space-4);
  --gv-btn-icon: var(--gv-size-icon-md);

  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  height: var(--gv-btn-height);
  padding: 0 var(--gv-btn-padding);
  border: 1px solid transparent;
  border-radius: var(--gv-radius-full);
  font: var(--gv-type-label-large);
  line-height: var(--gv-type-label-large-line);
  white-space: nowrap;
  cursor: pointer;
  transition:
    box-shadow var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.btn--xl {
  --gv-btn-height: var(--gv-size-control-xl);
}

.btn--lg {
  --gv-btn-height: var(--gv-size-control-lg);
}

.btn--md {
  --gv-btn-height: var(--gv-size-control-md);
}

.btn--sm {
  --gv-btn-height: var(--gv-size-control-sm);
  --gv-btn-padding: var(--gv-space-3);
  --gv-btn-icon: var(--gv-size-icon-dense);
}

.btn__icon {
  width: var(--gv-btn-icon);
  height: var(--gv-btn-icon);
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

.btn:not(:disabled):hover::after {
  opacity: var(--gv-state-hover);
}

.btn:not(:disabled):active::after {
  opacity: var(--gv-state-pressed);
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
}

.btn--danger.btn--filled {
  background: var(--gv-color-error);
  color: var(--gv-color-on-error);
}

.btn--danger.btn--tonal {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.btn--danger.btn--outlined,
.btn--danger.btn--text {
  color: var(--gv-color-error);
}

.btn--danger.btn--outlined {
  border-color: var(--gv-color-error);
}

/*
 * Disabled is layered (container 12% / content 38%), never one blanket
 * opacity: the old `.btn:disabled { opacity: .38 }` dropped the label to about
 * 1:1 in the dark theme. Filled uses a stronger content mix so the label keeps
 * >=3:1 against the layered container in the light theme as well.
 */
.btn:disabled {
  cursor: not-allowed;
}

.btn:disabled.btn--filled {
  background: color-mix(
    in srgb,
    var(--gv-color-on-surface) var(--gv-state-disabled-container),
    transparent
  );
  color: color-mix(in srgb, var(--gv-color-on-surface) 52%, transparent);
}

.btn:disabled.btn--tonal,
.btn:disabled.btn--outlined,
.btn:disabled.btn--text {
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

.btn:disabled.btn--outlined,
.btn:disabled.btn--text {
  background: transparent;
}

.btn--loading {
  cursor: progress;
}

.btn__spinner {
  width: var(--gv-btn-icon);
  height: var(--gv-btn-icon);
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
