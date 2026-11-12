<script setup lang="ts">
import { useI18n } from "vue-i18n";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import "@/views/gallery/i18n";

withDefaults(
  defineProps<{
    status?: "loading" | "ready" | "error";
    errorTitle?: string;
    errorBody?: string;
  }>(),
  {
    status: "ready",
    errorTitle: "",
    errorBody: "",
  },
);

defineEmits<{ retry: [] }>();

const { t } = useI18n();
</script>

<template>
  <section
    class="detail"
    data-testid="gallery-detail"
    :aria-busy="status === 'loading' || undefined"
  >
    <div v-if="status === 'loading'" class="detail__loading" data-testid="detail-loading">
      <Skeleton variant="list" :lines="3" />
      <Skeleton variant="line" :lines="3" />
    </div>

    <ErrorState
      v-else-if="status === 'error'"
      :title="errorTitle || t('gallery.loadFailed')"
      :body="errorBody"
      :retry-label="t('gallery.retry')"
      testid="detail-error"
      @retry="$emit('retry')"
    />

    <template v-else>
      <div v-if="$slots.header" class="detail__header">
        <slot name="header" />
      </div>

      <div v-if="$slots.actions" class="detail__actions">
        <slot name="actions" />
      </div>

      <div v-if="$slots.tags" class="detail__section detail__tags">
        <slot name="tags" />
      </div>

      <div v-if="$slots.thumbs" class="detail__section detail__thumbs">
        <slot name="thumbs" />
      </div>

      <div v-if="$slots.extra" class="detail__extra">
        <slot name="extra" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
}

.detail__loading {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.detail__header {
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.detail__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.detail__section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.detail__extra {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}
</style>
