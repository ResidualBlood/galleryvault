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
    /** Accessible name; also the hover title. Required by design. */
    label: string;
    /** Icon to render; the default slot remains supported for legacy callers. */
    name?: IconName;
    variant?: "standard" | "tonal" | "filled";
    /** `lg` / `md` / `sm`; legacy `default` inherits, `small` maps to `sm`. */
    size?: ControlSizeProp;
    disabled?: boolean;
    selected?: boolean;
    type?: "button" | "submit";
  }>(),
  {
    variant: "standard",
    size: "default",
    disabled: false,
    selected: false,
    type: "button",
  },
);

const size = useControlSize(props.size);
const iconSize = computed(() => controlIconSize(size.value));
</script>

<template>
  <button
    :type="type"
    data-gv-control
    :disabled="disabled"
    :aria-label="label"
    :aria-pressed="selected || undefined"
    :title="label"
    class="icon-btn"
    :class="[
      `icon-btn--${size}`,
      `icon-btn--${variant}`,
      { 'icon-btn--selected': selected },
    ]"
  >
    <Icon v-if="name" :name="name" :size="iconSize" class="icon-btn__icon" />
    <slot v-else />
  </button>
</template>

<style scoped>
.icon-btn {
  --gv-icon-btn-size: var(--gv-size-control-lg);
  --gv-icon-btn-icon: var(--gv-size-icon-md);

  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--gv-icon-btn-size);
  height: var(--gv-icon-btn-size);
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  cursor: pointer;
  transition:
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

/* Keep the visual square at the ladder step (40 at lg) while the hit area
   reaches --gv-size-touch (44). The pseudo-element never affects layout, so
   rows stay equal-height; consumers must leave >= 4px between buttons so two
   expanded targets cannot paint over each other (see DESIGN.md C12). */
.icon-btn::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: max(100%, var(--gv-size-touch));
  height: max(100%, var(--gv-size-touch));
  transform: translate(-50%, -50%);
  border-radius: inherit;
}

.icon-btn::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: currentColor;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.icon-btn:not(:disabled):hover::after {
  opacity: var(--gv-state-hover);
}

.icon-btn:not(:disabled):active::after {
  opacity: var(--gv-state-pressed);
}

.icon-btn--xl {
  --gv-icon-btn-size: var(--gv-size-control-xl);
}

.icon-btn--lg {
  --gv-icon-btn-size: var(--gv-size-control-lg);
}

.icon-btn--md {
  --gv-icon-btn-size: var(--gv-size-control-md);
}

.icon-btn--sm {
  --gv-icon-btn-size: var(--gv-size-control-sm);
  --gv-icon-btn-icon: var(--gv-size-icon-dense);
}

.icon-btn__icon {
  position: relative;
  width: var(--gv-icon-btn-icon);
  height: var(--gv-icon-btn-icon);
}

.icon-btn--tonal {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.icon-btn--filled {
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
}

.icon-btn--standard.icon-btn--selected {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.icon-btn--tonal.icon-btn--selected {
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.icon-btn--filled.icon-btn--selected {
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
}

.icon-btn:disabled {
  cursor: not-allowed;
  color: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-disabled), transparent);
}

.icon-btn--tonal:disabled,
.icon-btn--filled:disabled,
.icon-btn--standard.icon-btn--selected:disabled {
  background: color-mix(
    in srgb,
    var(--gv-color-on-surface) var(--gv-state-disabled-container),
    transparent
  );
}

@media (prefers-reduced-motion: reduce) {
  .icon-btn,
  .icon-btn::after {
    transition-duration: 1ms;
  }
}
</style>
