<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Select from "@/components/ui/Select.vue";
import { previewArchive, type ArchivePreview } from "@/api/archive";
import "./messages";

const props = withDefaults(
  defineProps<{
    open: boolean;
    gids: number[];
    defaultQuality?: "resample" | "original";
  }>(),
  {
    defaultQuality: "resample",
  },
);

const emit = defineEmits<{
  close: [];
  confirm: [payload: { gids: number[]; quality: "resample" | "original" }];
}>();

const { t } = useI18n();
const preview = ref<ArchivePreview | null>(null);
const quality = ref<"resample" | "original">("resample");
const loading = ref(false);
const error = ref("");
let seq = 0;

const qualityOptions = computed(() => [
  { value: "resample", label: t("system.archiveDialog.resample") },
  { value: "original", label: t("system.archiveDialog.original") },
]);

const items = computed(() => preview.value?.items ?? []);
const funds = computed(() =>
  typeof preview.value?.funds === "number" ? preview.value.funds.toLocaleString() : "—",
);

function formatSize(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function available(item: { resample_available?: boolean; original_available?: boolean }): boolean {
  return quality.value === "original" ? Boolean(item.original_available) : Boolean(item.resample_available);
}

function cost(item: {
  resample_cost?: number | null;
  original_cost?: number | null;
}): number | null {
  return quality.value === "original" ? item.original_cost ?? null : item.resample_cost ?? null;
}

function size(item: {
  resample_size?: number | null;
  original_size?: number | null;
}): number | null {
  return quality.value === "original" ? item.original_size ?? null : item.resample_size ?? null;
}

async function load(): Promise<void> {
  if (!props.open || props.gids.length === 0) return;
  const current = ++seq;
  loading.value = true;
  error.value = "";
  preview.value = null;
  try {
    const result = await previewArchive(props.gids);
    if (current === seq) preview.value = result;
  } catch (cause) {
    if (current === seq) {
      error.value = cause instanceof Error ? cause.message : t("system.archiveDialog.loadFailed");
    }
  } finally {
    if (current === seq) loading.value = false;
  }
}

watch(
  () => [props.open, props.gids] as const,
  ([open]) => {
    if (open) {
      quality.value = props.defaultQuality;
      void load();
    } else {
      seq += 1;
    }
  },
  { immediate: true },
);

function confirm(): void {
  if (!props.gids.length || error.value) return;
  emit("confirm", { gids: [...props.gids], quality: quality.value });
}
</script>

<template>
  <Dialog
    :open="open"
    :title="t('system.archiveDialog.title')"
    testid="archive-dialog"
    @close="emit('close')"
  >
    <p class="archive-dialog__subtitle">{{ t('system.archiveDialog.subtitle') }}</p>

    <p v-if="!gids.length" class="archive-dialog__empty">
      {{ t('system.archiveDialog.noSelection') }}
    </p>

    <template v-else>
      <p v-if="loading" class="archive-dialog__state">{{ t('system.archiveDialog.loading') }}</p>
      <p v-else-if="error" class="archive-dialog__error" role="alert">{{ error }}</p>

      <div v-else class="archive-dialog__body">
        <div class="archive-dialog__row">
          <span class="archive-dialog__funds">{{ t('system.archiveDialog.funds', { funds }) }}</span>
          <span class="archive-dialog__count">
            {{ t('system.archiveDialog.total', { count: items.length }) }}
          </span>
        </div>

        <Select v-model="quality" :options="qualityOptions" :label="t('system.archiveDialog.quality')" />

        <ul class="archive-dialog__list">
          <li v-for="item in items" :key="item.gid" class="archive-dialog__item">
            <span class="archive-dialog__title">{{ item.title || item.gid }}</span>
            <span v-if="item.error" class="archive-dialog__unavailable">{{ item.error }}</span>
            <span v-else-if="!available(item)" class="archive-dialog__unavailable">
              {{ t('system.archiveDialog.unavailable') }}
            </span>
            <span v-else class="archive-dialog__cost">
              {{
                t('system.archiveDialog.cost', {
                  cost: cost(item) ?? '—',
                  size: formatSize(size(item)),
                })
              }}
            </span>
          </li>
        </ul>
      </div>
    </template>

    <template #footer>
      <Button variant="text" @click="emit('close')">{{ t('system.archiveDialog.cancel') }}</Button>
      <Button
        :disabled="loading || Boolean(error) || !gids.length"
        data-testid="archive-dialog-confirm"
        @click="confirm"
      >
        {{ t('system.archiveDialog.confirm') }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.archive-dialog__subtitle {
  margin: 0 0 var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.archive-dialog__state {
  margin: 0;
  padding: var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.archive-dialog__empty {
  margin: 0;
  padding: var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.archive-dialog__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.archive-dialog__body {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.archive-dialog__row {
  display: flex;
  justify-content: space-between;
  gap: var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.archive-dialog__funds {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.archive-dialog__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  max-height: 40vh;
  overflow: auto;
}

.archive-dialog__item {
  display: flex;
  justify-content: space-between;
  gap: var(--gv-space-2);
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
  font: var(--gv-type-body-small);
}

.archive-dialog__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.archive-dialog__cost {
  color: var(--gv-color-on-surface-variant);
  white-space: nowrap;
}

.archive-dialog__unavailable {
  color: var(--gv-color-error);
  white-space: nowrap;
}
</style>
