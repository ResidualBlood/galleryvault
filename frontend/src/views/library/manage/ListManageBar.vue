<script setup lang="ts">
/**
 * Rename / delete row for local gallery lists.
 *
 * `POST /api/lists` already had a creation entry in `LibrarySaveBar`; the
 * PATCH/DELETE endpoints are kept by PLAN Q4, so this is their only UI.
 * Deleting the list that currently filters the page clears that filter through
 * the `cleared` event (the parent owns the query state).
 */
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import { ApiError } from "@/api/client";
import { deleteList, renameList, type GalleryList } from "@/api/lists";
import { useUiStore } from "@/stores/ui";

const props = defineProps<{
  lists: GalleryList[];
  /** Filter value currently applied by the page (stringified list id). */
  activeId?: string;
}>();

const emit = defineEmits<{
  "lists-changed": [];
  cleared: [];
}>();

const { t } = useI18n();
const ui = useUiStore();

const selectedId = ref("");
const busy = ref(false);
const error = ref("");

const selected = computed(
  () => props.lists.find((item) => String(item.id) === selectedId.value) ?? null,
);

const listOptions = computed(() => [
  { value: "", label: t("libraryManage.listManageSelect") },
  ...props.lists.map((item) => ({
    value: String(item.id),
    label: `${item.name} (${item.count ?? 0})`,
  })),
]);

watch(
  () => props.lists.map((item) => item.id).join(","),
  () => {
    if (!selected.value) selectedId.value = "";
  },
);

function message(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof Error) return cause.message;
  return String(cause);
}

/* -------------------------------------------------------------- rename list */

const renameOpen = ref(false);
const renameValue = ref("");

function openRename(): void {
  if (!selected.value) return;
  renameValue.value = selected.value.name;
  error.value = "";
  renameOpen.value = true;
}

async function submitRename(): Promise<void> {
  const target = selected.value;
  const name = renameValue.value.trim();
  if (!target || !name || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await renameList(target.id, name);
    ui.success(t("libraryManage.listRenamed"));
    renameOpen.value = false;
    emit("lists-changed");
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* -------------------------------------------------------------- delete list */

const deleteOpen = ref(false);

function openDelete(): void {
  if (!selected.value) return;
  error.value = "";
  deleteOpen.value = true;
}

async function confirmDelete(): Promise<void> {
  const target = selected.value;
  if (!target || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await deleteList(target.id);
    ui.success(t("libraryManage.listDeleted"));
    deleteOpen.value = false;
    if (props.activeId === String(target.id)) emit("cleared");
    selectedId.value = "";
    emit("lists-changed");
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="list-manage" data-testid="list-manage">
    <Select
      class="list-manage__select"
      data-testid="list-manage-select"
      :model-value="selectedId"
      :options="listOptions"
      :aria-label="t('libraryManage.listManageSelect')"
      @update:model-value="selectedId = $event"
    />
    <Button
      variant="text"
      :disabled="!selected || busy"
      data-testid="list-manage-rename"
      @click="openRename"
    >
      {{ t("libraryManage.listRename") }}
    </Button>
    <Button
      variant="text"
      danger
      :disabled="!selected || busy"
      data-testid="list-manage-delete"
      @click="openDelete"
    >
      {{ t("libraryManage.listDelete") }}
    </Button>

    <Dialog
      :open="renameOpen"
      :title="t('libraryManage.listRenameTitle')"
      testid="list-rename-dialog"
      @close="renameOpen = false"
    >
      <div class="list-manage__form">
        <Input
          v-model="renameValue"
          :label="t('libraryManage.listName')"
          :placeholder="t('libraryManage.listNamePlaceholder')"
          data-testid="list-rename-name"
          @enter="submitRename"
        />
        <p v-if="error" class="list-manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="renameOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          :disabled="!renameValue.trim() || busy"
          :loading="busy"
          data-testid="list-rename-submit"
          @click="submitRename"
        >
          {{ t("libraryManage.save") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="deleteOpen"
      :title="t('libraryManage.listDelete')"
      testid="list-delete-dialog"
      @close="deleteOpen = false"
    >
      <div class="list-manage__form">
        <p class="list-manage__hint">
          {{ t("libraryManage.listDeleteConfirm", { name: selected?.name ?? "" }) }}
        </p>
        <p v-if="error" class="list-manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="deleteOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          variant="filled"
          :loading="busy"
          data-testid="list-delete-confirm"
          @click="confirmDelete"
        >
          {{ t("libraryManage.confirm") }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.list-manage {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.list-manage__select {
  flex: none;
  width: 220px;
}

.list-manage__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.list-manage__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.list-manage__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

@media (max-width: 599.98px) {
  .list-manage__select {
    width: 100%;
  }
}
</style>
