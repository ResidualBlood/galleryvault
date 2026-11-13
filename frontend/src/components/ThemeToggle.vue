<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import IconButton from "@/components/ui/IconButton.vue";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();
const { t } = useI18n();

const glyph = computed(() => {
  if (settings.theme === "light") return "☀";
  if (settings.theme === "system") return "◐";
  return "☾";
});
</script>

<template>
  <IconButton
    :label="`${t('app.actions.theme')}: ${glyph}`"
    data-testid="theme-toggle"
    @click="settings.cycleTheme()"
  >
    <span class="theme-glyph" aria-hidden="true">{{ glyph }}</span>
  </IconButton>
</template>

<style scoped>
.theme-glyph {
  font: var(--gv-type-title-medium);
  line-height: 1;
}
</style>
