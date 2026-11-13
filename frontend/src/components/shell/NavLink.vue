<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { RouterLink } from "vue-router";
import Icon from "@/components/icons/Icon.vue";
import type { NavDestination } from "./navigation";

withDefaults(
  defineProps<{
    item: NavDestination;
    variant?: "drawer" | "rail" | "bottom";
  }>(),
  { variant: "drawer" },
);

const { t } = useI18n();
</script>

<template>
  <RouterLink
    :to="item.to"
    class="nav-link"
    :class="`nav-link--${variant}`"
    :data-nav="item.labelKey"
  >
    <span class="nav-link__indicator">
      <Icon :name="item.icon" size="lg" />
    </span>
    <span class="nav-link__label">{{ t(item.labelKey) }}</span>
  </RouterLink>
</template>

<style scoped>
.nav-link {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  min-height: 44px;
  margin: 0 var(--gv-space-2);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.nav-link:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.nav-link.router-link-active {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.nav-link__indicator {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-icon-lg);
  height: var(--gv-size-icon-lg);
}

.nav-link__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Rail: icon over a small label; the whole pill is the selection container. */
.nav-link--rail {
  flex-direction: column;
  gap: 2px;
  min-height: 48px;
  margin: 0 var(--gv-space-1);
  padding: 2px 0;
  border-radius: var(--gv-radius-md);
}

.nav-link--rail .nav-link__label {
  max-width: 100%;
  font: var(--gv-type-label-small);
  text-align: center;
}

/* Bottom bar: M3 navigation bar, the indicator pill carries the selection. */
.nav-link--bottom {
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-height: 0;
  margin: 0;
  padding: 0;
  border-radius: var(--gv-radius-md);
  font: var(--gv-type-label-small);
}

.nav-link--bottom.router-link-active {
  background: transparent;
  color: var(--gv-color-on-surface);
}

.nav-link--bottom .nav-link__indicator {
  width: 40px;
  height: 24px;
  border-radius: var(--gv-radius-full);
  transition: background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.nav-link--bottom.router-link-active .nav-link__indicator {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.nav-link--bottom .nav-link__label {
  font: var(--gv-type-label-small);
}
</style>
