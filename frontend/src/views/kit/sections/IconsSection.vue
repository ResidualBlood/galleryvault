<script setup lang="ts">
import Icon from "@/components/icons/Icon.vue";
import { iconNames } from "@/components/icons/registry";

const sizes = ["sm", "dense", "md", "lg"] as const;
</script>

<template>
  <section class="icons-section" aria-labelledby="kit-icons-title">
    <h2 id="kit-icons-title" class="icons-section__title">Icons</h2>
    <p class="icons-section__note">
      {{ iconNames.length }} semantic names · sizes sm / dense / md / lg (16 / 18 / 20 / 24)
    </p>
    <ul class="icons-grid">
      <li v-for="name in iconNames" :key="name" class="icons-grid__item">
        <span class="icons-grid__name">{{ name }}</span>
        <span class="icons-grid__sizes">
          <Icon v-for="size in sizes" :key="size" :name="name" :size="size" />
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.icons-section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-md);
}

.icons-section__title {
  margin: 0;
  font-size: var(--gv-type-title-large-size);
  line-height: var(--gv-type-title-large-line);
  color: var(--gv-color-on-surface);
}

.icons-section__note {
  margin: 0;
  font-size: var(--gv-type-body-small-size);
  line-height: var(--gv-type-body-small-line);
  color: var(--gv-color-on-surface-variant);
}

.icons-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--gv-space-sm);
  margin: 0;
  padding: 0;
  list-style: none;
}

.icons-grid__item {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-xs);
  padding: var(--gv-space-sm);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface);
}

.icons-grid__name {
  font-size: var(--gv-type-label-small-size);
  line-height: var(--gv-type-label-small-line);
  color: var(--gv-color-on-surface-variant);
}

.icons-grid__sizes {
  display: flex;
  align-items: center;
  gap: var(--gv-space-sm);
  min-height: var(--gv-size-icon-lg);
}
</style>
