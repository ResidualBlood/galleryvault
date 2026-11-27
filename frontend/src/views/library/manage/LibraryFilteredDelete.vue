<script setup lang="ts">
/**
 * "Delete every match of this filter" entry + its two-phase confirmation.
 *
 * Moved into the filter panel: it is a filter-scoped action, so it belongs
 * next to the filters instead of the flat batch row (audit LB-05 / LB-13), and
 * it stays reachable with an empty selection while the selection bar is gone.
 * The large-set guard (type the match count) is unchanged.
 */
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Switch from "@/components/ui/Switch.vue";
import { ApiError } from "@/api/client";
import {
  deleteGalleriesFiltered,
  type FilteredDeletePayload,
  type GalleryQuery,
} from "@/api/library";
import { useUiStore } from "@/stores/ui";

const props = defineProps<{ query: GalleryQuery }>();
const emit = defineEmits<{ removed: [] }>();

const { t } = useI18n();
const router = useRouter();
const ui = useUiStore();

function numeric(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

const filterPayload = computed<FilteredDeletePayload>(() => {
  const query = props.query;
  return {
    q: query.q?.trim() ?? "",
    category: query.category ?? "",
    tags: query.tags ?? "",
    tag_mode: query.tag_mode ?? "and",
    tag_match: query.tag_match ?? "exact",
    order_by: query.order_by && query.order_by !== "id_desc" ? query.order_by : undefined,
    read_status: query.read_status || undefined,
    min_rating: numeric(query.min_rating),
    page_min: numeric(query.page_min),
    page_max: numeric(query.page_max),
    size_min: numeric(query.size_min),
    size_max: numeric(query.size_max),
    posted_from: query.posted_from,
    posted_to: query.posted_to,
    uploader: query.uploader,
    image_quality: query.image_quality || undefined,
    min_local_rating: numeric(query.min_local_rating),
    list_id: numeric(query.list_id),
  };
});

const hasFilters = computed(() => {
  const payload = filterPayload.value;
  return Boolean(
    payload.q ||
      payload.category ||
      payload.tags ||
      payload.read_status ||
      payload.min_rating !== undefined ||
      payload.page_min !== undefined ||
      payload.page_max !== undefined ||
      payload.size_min !== undefined ||
      payload.size_max !== undefined ||
      payload.posted_from ||
      payload.posted_to ||
      payload.uploader ||
      payload.image_quality ||
      payload.min_local_rating !== undefined ||
      payload.list_id !== undefined,
  );
});

const filterSummary = computed(() => {
  const payload = filterPayload.value;
  const parts: string[] = [];
  if (payload.q) parts.push(`q: ${payload.q}`);
  if (payload.tags) parts.push(`tags: ${payload.tags}`);
  if (payload.category) parts.push(`category: ${payload.category}`);
  if (payload.read_status) parts.push(`read: ${payload.read_status}`);
  if (payload.list_id !== undefined) parts.push(`list: ${payload.list_id}`);
  return parts.length ? parts.join(" · ") : t("libraryManage.querySummaryDefault");
});

const open = ref(false);
const phase = ref<"confirm" | "typed">("confirm");
const matchCount = ref(0);
const confirmValue = ref("");
const deleteFiles = ref(false);
const busy = ref(false);
const error = ref("");

function message(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

function openDialog(): void {
  if (!hasFilters.value) return;
  phase.value = "confirm";
  matchCount.value = 0;
  confirmValue.value = "";
  deleteFiles.value = false;
  error.value = "";
  open.value = true;
}

const typedMismatch = computed(
  () =>
    phase.value === "typed" &&
    confirmValue.value.trim() !== "" &&
    confirmValue.value.trim() !== String(matchCount.value),
);

async function run(payload: FilteredDeletePayload): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    const result = await deleteGalleriesFiltered({
      ...filterPayload.value,
      ...payload,
    });
    ui.success(t("libraryManage.deletedCount", { count: result.deleted ?? 0 }));
    const failed = result.failed_deletions?.length ?? 0;
    if (failed) ui.error(t("libraryManage.deletedFailed", { count: failed }));
    open.value = false;
    emit("removed");
    // Legacy resets to the unfiltered library after a filtered delete.
    void router.push({ name: "library" });
  } catch (cause) {
    const detail = cause instanceof ApiError ? cause.detail : null;
    const code =
      detail && typeof detail === "object" && "code" in detail
        ? String((detail as { code?: unknown }).code)
        : "";
    if (code === "CONFIRM_REQUIRED") {
      const matched =
        detail && typeof detail === "object" && "matched" in detail
          ? Number((detail as { matched?: unknown }).matched)
          : 0;
      matchCount.value = Number.isFinite(matched) ? matched : 0;
      phase.value = "typed";
      confirmValue.value = "";
      return;
    }
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}

async function submit(): Promise<void> {
  if (busy.value) return;
  if (phase.value === "confirm") {
    await run({ delete_files: deleteFiles.value });
    return;
  }
  if (confirmValue.value.trim() !== String(matchCount.value)) return;
  await run({
    delete_files: deleteFiles.value,
    confirm: true,
    match_count: matchCount.value,
  });
}
</script>

<template>
  <Button
    variant="text"
    danger
    icon="delete"
    :disabled="!hasFilters"
    data-testid="filtered-delete"
    :title="hasFilters ? filterSummary : t('libraryManage.filteredDeleteEmpty')"
    @click="openDialog"
  >
    {{ t("libraryManage.filteredDelete") }}
  </Button>

  <Dialog
    :open="open"
    :title="phase === 'confirm' ? t('libraryManage.filteredDeleteTitle') : t('libraryManage.filteredDeleteLargeTitle')"
    testid="filtered-delete-dialog"
    @close="open = false"
  >
    <div class="filtered-delete__form">
      <p class="filtered-delete__hint">
        {{ t("libraryManage.filteredDeleteSummary", { summary: filterSummary }) }}
      </p>
      <p v-if="phase === 'confirm'" class="filtered-delete__hint">
        {{ t("libraryManage.filteredDeleteBody") }}
      </p>
      <p v-else class="filtered-delete__warning">
        {{ t("libraryManage.filteredDeleteLargeBody", { count: matchCount }) }}
      </p>
      <label class="filtered-delete__switch">
        <Switch v-model="deleteFiles" :label="t('libraryManage.deleteFilesToggle')" />
        <span>{{ t("libraryManage.deleteFilesToggle") }}</span>
      </label>
      <p class="filtered-delete__hint">{{ t("libraryManage.deleteFilesHint") }}</p>
      <Input
        v-if="phase === 'typed'"
        v-model="confirmValue"
        :label="t('libraryManage.filteredDeleteTypeHint', { count: matchCount })"
        :error="typedMismatch ? t('libraryManage.filteredDeleteMismatch') : ''"
        data-testid="filtered-delete-count"
        @enter="submit"
      />
      <p v-if="error" class="filtered-delete__error">{{ error }}</p>
    </div>
    <template #footer>
      <Button variant="text" @click="open = false">
        {{ t("libraryManage.cancel") }}
      </Button>
      <Button
        variant="filled"
        danger
        :disabled="phase === 'typed' && confirmValue.trim() !== String(matchCount)"
        :loading="busy"
        data-testid="filtered-delete-confirm"
        @click="submit"
      >
        {{ t("libraryManage.deleteConfirm") }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.filtered-delete__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.filtered-delete__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.filtered-delete__warning {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-medium);
}

.filtered-delete__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.filtered-delete__switch {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}
</style>
