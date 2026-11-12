<script setup lang="ts">
import { computed } from "vue";

export type BadgeTone = "neutral" | "primary" | "tertiary" | "error" | "success" | "category";

export interface GalleryBadge {
  label: string;
  tone?: BadgeTone;
  /** For `tone: "category"`, the `--gv-cat-*` token name (without `var()`). */
  colorToken?: string;
  title?: string;
}

const props = withDefaults(
  defineProps<{
    badges?: GalleryBadge[];
    /** Same-group limit from DESIGN.md C04; extra badges collapse to "+N". */
    max?: number;
    align?: "start" | "end";
  }>(),
  {
    badges: () => [],
    max: 3,
    align: "start",
  },
);

const visible = computed<GalleryBadge[]>(() => {
  const badges = props.badges.filter((badge) => badge.label);
  if (props.max <= 0 || badges.length <= props.max) return badges;
  const overflow = badges.length - (props.max - 1);
  return [...badges.slice(0, props.max - 1), { label: `+${overflow}`, tone: "neutral" }];
});

function badgeStyle(badge: GalleryBadge): Record<string, string> {
  if (!badge.colorToken) return {};
  return {
    "--badge-bg": `var(${badge.colorToken})`,
    "--badge-ink": `var(${badge.colorToken}-ink)`,
  };
}
</script>

<template>
  <span class="badge-strip" :class="`badge-strip--${align}`" aria-hidden="true">
    <span
      v-for="(badge, index) in visible"
      :key="`${badge.label}-${index}`"
      class="badge"
      :class="`badge--${badge.tone ?? 'neutral'}`"
      :style="badgeStyle(badge)"
      :title="badge.title"
    >
      {{ badge.label }}
    </span>
  </span>
</template>

<style scoped>
.badge-strip {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--gv-space-1);
  min-width: 0;
  max-width: 100%;
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  min-width: 20px;
  padding: 0 var(--gv-space-2);
  overflow: hidden;
  border-radius: var(--gv-radius-xs);
  background: var(--badge-bg, var(--gv-color-secondary-container));
  color: var(--badge-ink, var(--gv-color-on-secondary-container));
  font: var(--gv-type-label-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge--primary {
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
}

.badge--tertiary {
  background: var(--gv-color-tertiary);
  color: var(--gv-color-on-tertiary);
}

.badge--error {
  background: var(--gv-color-error);
  color: var(--gv-color-on-error);
}

.badge--success {
  background: var(--gv-color-success);
  color: var(--gv-color-on-success);
}

.badge--category {
  background: var(--badge-bg, var(--gv-color-secondary-container));
  color: var(--badge-ink, var(--gv-color-on-secondary-container));
}
</style>
