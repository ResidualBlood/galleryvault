<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import Tabs, { type TabItem } from "@/components/ui/Tabs.vue";

/**
 * Maintenance section switcher shared by the duplicate views.
 *
 * The audit found the old hand-written tab bar wrapping into two ragged rows at
 * 390 (DP-08 / DX-09 / FM-04) and the ignored page highlighting the wrong tab
 * (FI-01). The shared `Tabs` component scrolls horizontally instead of wrapping
 * and this wrapper derives the active tab from the route, so the highlight can
 * never disagree with the page. The ignored page is a secondary view and does
 * not render this bar at all.
 */
const route = useRoute();
const { t } = useI18n();

const items = computed<TabItem[]>(() => [
  { value: "recycle", label: t("maintenance.shared.tabs.recycle"), to: "/recycle" },
  { value: "duplicates", label: t("maintenance.shared.tabs.duplicates"), to: "/duplicates" },
  {
    value: "favorites",
    label: t("maintenance.shared.tabs.favorites"),
    to: "/duplicates/favorites",
  },
  {
    value: "crossGid",
    label: t("maintenance.shared.tabs.crossGid"),
    to: "/duplicates/cross-gid",
  },
  { value: "integrity", label: t("maintenance.shared.tabs.integrity"), to: "/integrity" },
  { value: "archive", label: t("maintenance.shared.tabs.archive"), to: "/archive" },
]);

const ACTIVE: Record<string, string> = {
  recycle: "recycle",
  duplicates: "duplicates",
  "favorites-manage": "favorites",
  "duplicates-cross-gid": "crossGid",
  integrity: "integrity",
  archive: "archive",
};

const active = computed(() => ACTIVE[String(route.name ?? "")] ?? "");
</script>

<template>
  <Tabs
    :items="items"
    :active="active"
    :label="t('maintenance.shared.tabsLabel')"
    testid="maintenance-tabs"
  />
</template>
