<script setup lang="ts">
import { computed } from "vue";
import { iconRegistry, type IconName } from "./registry";

/**
 * One inline SVG icon, addressed by semantic name. Dimensions come from the
 * `--gv-size-icon-*` tokens (16 / 18 / 20 / 24) and colour from
 * `currentColor`; no inline styles and no runtime icon requests.
 */
const props = withDefaults(
  defineProps<{
    name: IconName;
    size?: "sm" | "dense" | "md" | "lg";
    label?: string;
  }>(),
  { size: "md" },
);

const icon = computed(() => iconRegistry[props.name]);
</script>

<template>
  <component
    :is="icon"
    class="gv-icon"
    :class="`gv-icon--${size}`"
    :role="label ? 'img' : undefined"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
    focusable="false"
  />
</template>

<style scoped>
.gv-icon {
  display: block;
  flex: none;
  fill: currentColor;
  color: inherit;
}

.gv-icon--sm {
  width: var(--gv-size-icon-sm);
  height: var(--gv-size-icon-sm);
}

/* `--gv-size-icon-dense` is not in tokens.css yet; the fallback keeps the
   18px dense step local to the icon component until it is promoted. */
.gv-icon--dense {
  width: var(--gv-size-icon-dense, 18px);
  height: var(--gv-size-icon-dense, 18px);
}

.gv-icon--md {
  width: var(--gv-size-icon-md);
  height: var(--gv-size-icon-md);
}

.gv-icon--lg {
  width: var(--gv-size-icon-lg);
  height: var(--gv-size-icon-lg);
}
</style>
