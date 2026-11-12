<script setup lang="ts">
/**
 * Placeholder for the unified card/detail/reader action row (fe-quick-actions).
 * Buttons are intentionally inert until the favorite/download stores exist.
 */
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import IconButton from "@/components/ui/IconButton.vue";

withDefaults(defineProps<{ disabled?: boolean }>(), { disabled: true });
defineEmits<{ read: []; favorite: []; download: [] }>();

const { t } = useI18n();
</script>

<template>
  <div class="gallery-actions" data-testid="gallery-actions">
    <Button variant="filled" :disabled="disabled" @click="$emit('read')">
      {{ t("app.actions.read") }}
    </Button>
    <IconButton
      :label="t('app.nav.favorites')"
      :disabled="disabled"
      data-testid="gallery-favorite"
      @click="$emit('favorite')"
    >
      <span aria-hidden="true">♡</span>
    </IconButton>
    <IconButton
      :label="t('app.nav.downloads')"
      :disabled="disabled"
      data-testid="gallery-download"
      @click="$emit('download')"
    >
      <span aria-hidden="true">⇩</span>
    </IconButton>
  </div>
</template>

<style scoped>
.gallery-actions {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
}
</style>
