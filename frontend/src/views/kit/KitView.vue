<script setup lang="ts">
import { type Component } from "vue";

/**
 * Component kit (`#/_kit`): a shared, browser-reachable specimen page for the
 * polish phase. Sections are auto-collected from `./sections/*.vue` so later
 * batches (icons, controls, layout kit, collection browse, tag UI) can drop a
 * file in without touching this view or the router. Deliberately absent from
 * the navigation.
 */
interface KitSection {
  path: string;
  component: Component;
}

const modules = import.meta.glob<{ default: Component }>("./sections/*.vue", {
  eager: true,
});

const sections: KitSection[] = Object.entries(modules)
  .sort(([a], [b]) => a.localeCompare(b))
  .map(([path, module]) => ({ path, component: module.default }));
</script>

<template>
  <section class="kit" data-testid="kit-view">
    <header class="kit__header">
      <p class="kit__eyebrow">Design kit</p>
      <h1 class="kit__title">Component specimen</h1>
      <p class="kit__lede">
        Shared baseline for the polish phase: control ladder, tag namespace palette, and
        browser-level alignment / screenshot fixtures. Not linked from the navigation.
      </p>
    </header>
    <component :is="section.component" v-for="section in sections" :key="section.path" />
  </section>
</template>

<style scoped>
.kit {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-6);
  max-width: var(--gv-size-content-max);
}

.kit__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.kit__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.kit__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.kit__lede {
  margin: 0;
  max-width: 72ch;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}
</style>
