<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Tabs, { type TabItem } from "@/components/ui/Tabs.vue";

const props = defineProps<{ active: string }>();
const { t } = useI18n();
const router = useRouter();

/** Destinations are resolved once so the shared Tabs component can render links. */
const tabs = computed<TabItem[]>(() =>
  [
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
  ].map((tab) => ({
    value: tab.key,
    label: tab.label,
    to: router.resolve({ name: tab.name }).fullPath,
  })),
);
</script>

<template>
  <Tabs
    :items="tabs"
    :active="props.active"
    :label="t('maintenance.shared.tabs.label')"
    testid="maintenance-tabs"
  />
</template>
