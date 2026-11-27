<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import IconButton from "@/components/ui/IconButton.vue";
import type { IconName } from "@/components/icons/registry";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();
const { t } = useI18n();

/**
 * SH-01 / LG-01: the theme control used to render ☀ / ◐ / ☾ as text at three
 * different optical sizes. The icon now comes from the shared registry and the
 * current state is carried by the label instead of a glyph.
 */
const icon = computed<IconName>(() => {
  if (settings.theme === "light") return "theme-light";
  if (settings.theme === "system") return "theme-system";
  return "theme-dark";
});

const stateLabel = computed(() => {
  if (settings.theme === "light") return t("app.actions.themeLight");
  if (settings.theme === "system") return t("app.actions.themeSystem");
  return t("app.actions.themeDark");
});

const label = computed(() => `${t("app.actions.theme")}: ${stateLabel.value}`);
</script>

<template>
  <IconButton
    :name="icon"
    :label="label"
    data-testid="theme-toggle"
    @click="settings.cycleTheme()"
  />
</template>
