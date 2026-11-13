<!-- gv-polish:pending -->
<script setup lang="ts">
import { useI18n } from "vue-i18n";
import IconButton from "@/components/ui/IconButton.vue";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();
const { t } = useI18n();
</script>

<template>
  <IconButton
    :label="t('app.actions.language')"
    :selected="settings.lang === 'en'"
    data-testid="lang-toggle"
    @click="settings.toggleLang()"
  >
    <span class="lang-glyph" aria-hidden="true">{{ settings.lang === "zh" ? "中" : "EN" }}</span>
  </IconButton>
</template>

<style scoped>
.lang-glyph {
  font: var(--gv-type-label-large);
  line-height: 1;
}
</style>
