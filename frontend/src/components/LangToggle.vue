<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import IconButton from "@/components/ui/IconButton.vue";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();
const { t } = useI18n();

/**
 * LG-01: the language control used to be a single CJK character at 14px. A globe
 * icon carries the meaning; the two-letter locale code stays as a readable badge
 * (also what the parity test asserts).
 */
const badge = computed(() => (settings.lang === "zh" ? "ZH" : "EN"));
const label = computed(() => `${t("app.actions.language")} (${badge.value})`);
</script>

<template>
  <IconButton
    :label="label"
    :selected="settings.lang === 'en'"
    data-testid="lang-toggle"
    @click="settings.toggleLang()"
  >
    <span class="lang-toggle">
      <Icon name="language" size="md" />
      <span class="lang-toggle__badge" aria-hidden="true">{{ badge }}</span>
    </span>
  </IconButton>
</template>

<style scoped>
.lang-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.lang-toggle__badge {
  position: absolute;
  right: calc(-1 * var(--gv-space-2));
  bottom: calc(-1 * var(--gv-space-1));
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  line-height: 1;
}
</style>
