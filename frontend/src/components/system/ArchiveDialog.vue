<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Select from "@/components/ui/Select.vue";
import {
  previewArchive,
  type ArchivePreview,
  type ArchivePreviewItem,
} from "@/api/archive";
import { fetchSettings } from "@/api/settings";
import "./messages";

type Quality = "resample" | "original";

/** Backend default (`config.py: archive_quality`) when the read fails. */
const FALLBACK_QUALITY: Quality = "resample";

function normalizeQuality(value: unknown): Quality {
  return value === "original" || value === "resample" ? value : FALLBACK_QUALITY;
}

type TierItem = Pick<
  ArchivePreviewItem,
  | "resample_cost"
  | "resample_size"
  | "original_cost"
  | "original_size"
  | "resample_available"
  | "original_available"
>;

/**
 * `defaultQuality` is an explicit caller override (used by the settings
 * harness); without it the dialog follows the backend `archive_quality`
 * setting, so a shared dialog no longer hard-codes resample.
 */
const props = defineProps<{
  open: boolean;
  gids: number[];
  defaultQuality?: Quality;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [payload: { gids: number[]; quality: Quality }];
}>();

const { t } = useI18n();
const preview = ref<ArchivePreview | null>(null);
const quality = ref<Quality>(FALLBACK_QUALITY);
const loading = ref(false);
const error = ref("");
let seq = 0;
let settingsSeq = 0;
let qualityPicked = false;
let controller: AbortController | null = null;

const qualityOptions = computed(() => [
  { value: "resample", label: t("system.archiveDialog.resample") },
  { value: "original", label: t("system.archiveDialog.original") },
]);

const items = computed(() => preview.value?.items ?? []);
const funds = computed(() =>
  typeof preview.value?.funds === "number" ? preview.value.funds.toLocaleString() : "—",
);

/** Legacy disables confirmation when every preview row failed. */
const allFailed = computed(
  () => items.value.length > 0 && items.value.every((item) => Boolean(item.error)),
);

const confirmDisabled = computed(
  () =>
    loading.value ||
    Boolean(error.value) ||
    props.gids.length === 0 ||
    items.value.length === 0 ||
    allFailed.value,
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

function tierAvailable(item: TierItem, tier: Quality): boolean {
  return tier === "original"
    ? Boolean(item.original_available)
    : Boolean(item.resample_available);
}

function tierCost(item: TierItem, tier: Quality): number | null {
  return tier === "original" ? item.original_cost ?? null : item.resample_cost ?? null;
}

function tierSize(item: TierItem, tier: Quality): number | null {
  return tier === "original" ? item.original_size ?? null : item.resample_size ?? null;
}

function qualityLabel(tier: Quality): string {
  return t(
    tier === "original" ? "system.archiveDialog.original" : "system.archiveDialog.resample",
  );
}

/** Same "GP · size" shape as the legacy archive table, prefixed when unaffordable. */
function tierText(item: TierItem, tier: Quality): string {
  const cost = tierCost(item, tier);
  if (cost === null) return "N/A";
  const prefix = tierAvailable(item, tier) ? "" : "⚠ ";
  return `${prefix}${cost} GP · ${formatSize(tierSize(item, tier))}`;
}

function abortPreview(): void {
  controller?.abort();
  controller = null;
}

async function load(): Promise<void> {
  if (!props.open || props.gids.length === 0) return;
  const current = ++seq;
  abortPreview();
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  preview.value = null;
  try {
    const result = await previewArchive(props.gids, controller.signal);
    if (current === seq) preview.value = result;
  } catch (cause) {
    if (current !== seq) return;
    if (cause instanceof DOMException && cause.name === "AbortError") return;
    error.value =
      cause instanceof Error ? cause.message : t("system.archiveDialog.loadFailed");
  } finally {
    if (current === seq) loading.value = false;
  }
}

/**
 * Read `archive_quality` from GET /api/settings. The preview request runs in
 * parallel; a selection made while the read is in flight wins, so the answer
 * cannot overwrite the user's own choice.
 */
async function applyConfiguredQuality(): Promise<void> {
  if (props.defaultQuality) return;
  const token = ++settingsSeq;
  try {
    const settings = await fetchSettings();
    if (token !== settingsSeq || qualityPicked) return;
    quality.value = normalizeQuality(settings.archive_quality);
  } catch {
    if (token === settingsSeq && !qualityPicked) quality.value = FALLBACK_QUALITY;
  }
}

function onQualityChange(): void {
  qualityPicked = true;
}

watch(
  () => [props.open, props.gids] as const,
  ([open]) => {
    if (open && props.gids.length > 0) {
      qualityPicked = false;
      quality.value = props.defaultQuality ?? FALLBACK_QUALITY;
      void applyConfiguredQuality();
      void load();
      return;
    }
    settingsSeq += 1;
    seq += 1;
    abortPreview();
    preview.value = null;
    loading.value = false;
    error.value = "";
  },
  { immediate: true },
);

function confirm(): void {
  if (confirmDisabled.value) return;
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
      <div v-else-if="error" class="archive-dialog__failure">
        <p class="archive-dialog__error" role="alert">{{ error }}</p>
        <Button
          variant="outlined"
          size="compact"
          data-testid="archive-dialog-retry"
          @click="load"
        >
          {{ t('system.archiveDialog.retry') }}
        </Button>
      </div>

      <div v-else class="archive-dialog__body">
        <div class="archive-dialog__row">
          <span class="archive-dialog__funds">{{ t('system.archiveDialog.funds', { funds }) }}</span>
          <span class="archive-dialog__count">
            {{ t('system.archiveDialog.total', { count: items.length }) }}
          </span>
        </div>

        <Select
          v-model="quality"
          :options="qualityOptions"
          :label="t('system.archiveDialog.quality')"
          @change="onQualityChange"
        />

        <p v-if="!items.length" class="archive-dialog__empty">
          {{ t('system.archiveDialog.noItems') }}
        </p>

        <p v-else-if="allFailed" class="archive-dialog__error" role="alert">
          {{ items.find((item) => item.error)?.error }}
        </p>

        <ul class="archive-dialog__list">
          <li v-for="item in items" :key="item.gid" class="archive-dialog__item">
            <span class="archive-dialog__title">{{ item.title || item.gid }}</span>
            <span v-if="item.error" class="archive-dialog__unavailable">{{ item.error }}</span>
            <span v-else class="archive-dialog__costs">
              <span
                v-for="tier in (['original', 'resample'] as const)"
                :key="tier"
                class="archive-dialog__cost"
                :class="{ 'archive-dialog__cost--unavailable': !tierAvailable(item, tier) }"
              >
                {{ qualityLabel(tier) }}: {{ tierText(item, tier) }}
              </span>
            </span>
          </li>
        </ul>
      </div>
    </template>

    <template #footer>
      <Button variant="text" @click="emit('close')">{{ t('system.archiveDialog.cancel') }}</Button>
      <Button
        :disabled="confirmDisabled"
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

.archive-dialog__failure {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--gv-space-2);
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
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
  font: var(--gv-type-body-small);
}

.archive-dialog__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gv-color-on-surface);
}

.archive-dialog__costs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.archive-dialog__cost {
  color: var(--gv-color-on-surface-variant);
  white-space: nowrap;
}

.archive-dialog__cost--unavailable {
  color: var(--gv-color-error);
}

.archive-dialog__unavailable {
  color: var(--gv-color-error);
  white-space: nowrap;
}
</style>
