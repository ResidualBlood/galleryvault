<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";

const props = defineProps<{
  page: number;
  pages: number;
  total?: number;
  pageSize?: number;
  testid?: string;
}>();

const emit = defineEmits<{ change: [page: number] }>();
const { t } = useI18n();

const safePages = computed(() => Math.max(1, props.pages));
const summary = computed(() =>
  t("maintenance.shared.page", { page: props.page, pages: safePages.value }),
);

function go(page: number): void {
  if (page < 1 || page > safePages.value || page === props.page) return;
  emit("change", page);
}
</script>

<template>
  <nav class="pager" :data-testid="testid ?? 'pager'" :aria-label="summary">
    <Button
      variant="outlined"
      size="compact"
      :disabled="page <= 1"
      data-testid="pager-prev"
      @click="go(page - 1)"
    >
      {{ t("maintenance.shared.prev") }}
    </Button>
    <span class="pager__summary">
      {{ summary }}
      <template v-if="total !== undefined"> · {{ total }}</template>
    </span>
    <Button
      variant="outlined"
      size="compact"
      :disabled="page >= safePages"
      data-testid="pager-next"
      @click="go(page + 1)"
    >
      {{ t("maintenance.shared.next") }}
    </Button>
  </nav>
</template>

<style scoped>
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-4);
}

.pager__summary {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
