<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";

const props = defineProps<{ active: string }>();
const { t } = useI18n();

const tabs = computed(() => [
  { key: "recycle", name: "recycle", label: t("maintenance.shared.tabs.recycle") },
  { key: "duplicates", name: "duplicates", label: t("maintenance.shared.tabs.duplicates") },
  {
    key: "favmanage",
    name: "favorites-manage",
    label: t("maintenance.shared.tabs.favorites"),
  },
  {
    key: "dupxgid",
    name: "duplicates-cross-gid",
    label: t("maintenance.shared.tabs.crossGid"),
  },
  { key: "integrity", name: "integrity", label: t("maintenance.shared.tabs.integrity") },
  { key: "archive", name: "archive", label: t("maintenance.shared.tabs.archive") },
]);
</script>

<template>
  <nav class="tabs" role="tablist" data-testid="maintenance-tabs">
    <RouterLink
      v-for="tab in tabs"
      :key="tab.key"
      class="tabs__link"
      :class="{ 'tabs__link--active': props.active === tab.key }"
      :to="{ name: tab.name }"
      role="tab"
      :aria-selected="props.active === tab.key"
    >
      {{ tab.label }}
    </RouterLink>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.tabs__link {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-xs);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.tabs__link:hover {
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
}

.tabs__link--active {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}
</style>
