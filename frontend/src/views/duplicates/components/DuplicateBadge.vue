<script setup lang="ts">
import Icon from "@/components/icons/Icon.vue";
import type { IconName } from "@/components/icons/registry";

/**
 * Static metadata chip used inside duplicate group headers and copy rows.
 *
 * Group-header chips are one control-ladder step (`sm`, 32px) so they line up
 * with the group action beside them (DP-03). Copy metadata uses the denser
 * `xs` step so the title / tags / meta stack stays compact.
 */
withDefaults(
  defineProps<{
    tone?: "neutral" | "primary" | "warning" | "success" | "error";
    size?: "sm" | "xs";
    icon?: IconName;
  }>(),
  { tone: "neutral", size: "xs", icon: undefined },
);
</script>

<template>
  <span class="dup-badge" :class="[`dup-badge--${tone}`, `dup-badge--${size}`]">
    <Icon v-if="icon" :name="icon" :size="size === 'sm' ? 'dense' : 'sm'" />
    <span class="dup-badge__text"><slot /></span>
  </span>
</template>

<style scoped>
.dup-badge {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.dup-badge--sm {
  min-height: var(--gv-size-control-sm);
  font: var(--gv-type-label-medium);
}

.dup-badge--xs {
  min-height: var(--gv-size-tag);
}

.dup-badge--primary {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.dup-badge--warning {
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
}

.dup-badge--success {
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
}

.dup-badge--error {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.dup-badge__text {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
