<script setup lang="ts">
import Dialog from "@/components/ui/Dialog.vue";
import Button from "@/components/ui/Button.vue";
import { useI18n } from "vue-i18n";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    body?: string;
    confirmLabel?: string;
    danger?: boolean;
    testid?: string;
  }>(),
  {
    body: "",
    confirmLabel: "",
    danger: false,
    testid: "confirm-dialog",
  },
);

const emit = defineEmits<{ confirm: []; cancel: [] }>();
const { t } = useI18n();
</script>

<template>
  <Dialog
    :open="props.open"
    :title="props.title"
    :testid="props.testid"
    @close="emit('cancel')"
  >
    <p v-if="props.body" class="confirm__body">{{ props.body }}</p>
    <slot />
    <template #footer>
      <Button variant="outlined" data-testid="confirm-cancel" @click="emit('cancel')">
        {{ t("maintenance.shared.cancel") }}
      </Button>
      <Button
        :variant="props.danger ? 'filled' : 'tonal'"
        :class="{ 'confirm__danger': props.danger }"
        data-testid="confirm-accept"
        @click="emit('confirm')"
      >
        {{ props.confirmLabel || t("maintenance.shared.confirm") }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.confirm__body {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.confirm__danger {
  background: var(--gv-color-error);
  color: var(--gv-color-on-error);
}
</style>
