<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import EmptyState from "@/components/ui/EmptyState.vue";

const route = useRoute();
const { t } = useI18n();

const titleKey = computed(() => {
  const meta = route.meta.title;
  return typeof meta === "string" ? meta : "app.title";
});
</script>

<template>
  <section class="placeholder" data-testid="placeholder">
    <p class="placeholder__badge">{{ t("app.placeholder.badge") }}</p>
    <EmptyState
      :title="t('app.placeholder.title')"
      :body="t('app.placeholder.body')"
      testid="placeholder-empty"
    />
    <p class="placeholder__route">
      <span>{{ t("app.placeholder.route") }}</span>
      <code>{{ route.fullPath }}</code>
      <span class="sr-only">{{ t(titleKey) }}</span>
    </p>
  </section>
</template>

<style scoped>
.placeholder {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.placeholder__badge {
  align-self: flex-start;
  margin: 0;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
}

.placeholder__route {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.placeholder__route code {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
}
</style>
