<script setup lang="ts">
/**
 * Row actions for the reading history.
 *
 * Both controls come from the shared Button so the height matches the other
 * collection rows. Below 600px the labels collapse to icons to keep the row
 * inside the viewport (audit HS-06); the accessible names never change.
 */
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import type { GalleryItem } from "@/api/library";

const props = defineProps<{
  item: GalleryItem;
  readPage?: number;
  /** Grid cards and table rows only have room for the icon buttons. */
  iconOnly?: boolean;
}>();

const emit = defineEmits<{ reset: [] }>();

const router = useRouter();
const { t } = useI18n();

const readerTo = computed(() => `/reader/${props.item.id}/${props.readPage ?? 0}`);

function openReader(): void {
  void router.push(readerTo.value);
}
</script>

<template>
  <div class="history-actions" :class="{ 'history-actions--icon-only': iconOnly }">
    <Button
      variant="text"
      size="sm"
      icon="play"
      :aria-label="t('legacy.readNow')"
      :title="t('legacy.readNow')"
      data-testid="history-open-row"
      @click.stop="openReader"
    >
      <span class="history-actions__label">{{ t("legacy.readNow") }}</span>
    </Button>
    <Button
      variant="text"
      size="sm"
      icon="retry"
      :aria-label="t('history.page.clearSingle')"
      :title="t('legacy.markUnread')"
      data-testid="history-reset-row"
      @click.stop="emit('reset')"
    >
      <span class="history-actions__label">{{ t("history.page.clearSingle") }}</span>
    </Button>
  </div>
</template>

<style scoped>
.history-actions {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
}

.history-actions--icon-only .history-actions__label {
  display: none;
}

@media (max-width: 599.98px) {
  .history-actions__label {
    display: none;
  }
}
</style>
