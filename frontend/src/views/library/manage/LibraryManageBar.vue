<script setup lang="ts">
/**
 * Batch actions for the local library.
 *
 * The old block always rendered a management card with five same-weight 32px
 * buttons, disabled until something was selected (audit LB-05 / LB-13). The
 * actions now live in the shared `SelectionBar`: it only exists while a
 * selection exists, the primary actions use the outlined variant, and the
 * destructive one sits in the danger slot at the end.
 *
 * Flows are unchanged: batch favourite still follows the cloud result, adding to
 * a list still accepts an existing list or a new name, and deleting still asks
 * for confirmation twice (files toggle on the first step).
 */
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Switch from "@/components/ui/Switch.vue";
import { ApiError } from "@/api/client";
import {
  addGalleriesToFavorites,
  deleteGalleriesBulk,
  type GalleryItem,
} from "@/api/library";
import { addListItems, createList, type GalleryList } from "@/api/lists";
import { fetchFavoriteCategories, type FavoriteCategory } from "@/api/favorites";
import { useUiStore } from "@/stores/ui";
import { ensureLibraryManageMessages } from "./messages";

ensureLibraryManageMessages();

const props = withDefaults(
  defineProps<{
    selected: GalleryItem[];
    lists: GalleryList[];
    /** List currently filtered in the URL; preselected in the add-to-list dialog. */
    defaultListId?: string;
  }>(),
  { defaultListId: "" },
);

const emit = defineEmits<{
  clear: [];
  removed: [ids: number[], deleted: number];
  favorited: [gids: number[]];
}>();

const { t } = useI18n();
const ui = useUiStore();

const favoriteCategories = ref<FavoriteCategory[]>([]);
const busy = ref(false);
const error = ref("");

const selectedCount = computed(() => props.selected.length);

function numeric(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

const targetListOptions = computed(() => [
  { value: "", label: t("libraryManage.listAddTarget") },
  ...props.lists.map((item) => ({
    value: String(item.id),
    label: `${item.name} (${item.count ?? 0})`,
  })),
]);

const favoriteOptions = computed(() =>
  favoriteCategories.value.map((item) => ({
    value: String(item.favcat),
    label: item.name || `favcat ${item.favcat}`,
  })),
);

function message(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

/* ------------------------------------------------------------------- lists */

const addListOpen = ref(false);
const addListTarget = ref("");
const addListNewName = ref("");

function openAddToList(): void {
  if (!selectedCount.value) {
    ui.info(t("libraryManage.listAddEmpty"));
    return;
  }
  addListTarget.value = props.defaultListId;
  addListNewName.value = "";
  error.value = "";
  addListOpen.value = true;
}

async function submitAddToList(): Promise<void> {
  if (!selectedCount.value || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    let listId = numeric(addListTarget.value);
    const newName = addListNewName.value.trim();
    if (newName) {
      const created = await createList(newName);
      listId = created.id;
    }
    if (!listId) {
      error.value = t("libraryManage.listAddTarget");
      return;
    }
    const ids = props.selected.map((item) => item.id);
    const result = await addListItems(listId, ids);
    ui.success(t("libraryManage.listAddDone", { count: result.added ?? ids.length }));
    addListOpen.value = false;
    emit("clear");
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* ------------------------------------------------------------ batch delete */

const deleteOpen = ref(false);
const deleteStep = ref<1 | 2>(1);
const deleteFiles = ref(false);

function openBatchDelete(): void {
  if (!selectedCount.value) {
    ui.info(t("libraryManage.batchFavoriteEmpty"));
    return;
  }
  deleteStep.value = 1;
  deleteFiles.value = false;
  error.value = "";
  deleteOpen.value = true;
}

async function confirmBatchDelete(): Promise<void> {
  if (busy.value) return;
  if (deleteStep.value === 1) {
    deleteStep.value = 2;
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const ids = props.selected.map((item) => item.id);
    const result = await deleteGalleriesBulk(ids, deleteFiles.value);
    const deleted = result.deleted ?? ids.length;
    ui.success(t("libraryManage.deletedCount", { count: deleted }));
    const failed = result.failed_deletions?.length ?? 0;
    if (failed) ui.error(t("libraryManage.deletedFailed", { count: failed }));
    deleteOpen.value = false;
    emit("clear");
    emit("removed", ids, deleted);
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* ---------------------------------------------------------- batch favourite */

const favOpen = ref(false);
const favTarget = ref("0");

async function openBatchFavorite(): Promise<void> {
  if (!selectedCount.value) {
    ui.info(t("libraryManage.batchFavoriteEmpty"));
    return;
  }
  error.value = "";
  favOpen.value = true;
  if (!favoriteCategories.value.length) {
    try {
      favoriteCategories.value = await fetchFavoriteCategories();
    } catch {
      favoriteCategories.value = [];
    }
  }
  if (!favoriteOptions.value.length) {
    favoriteCategories.value = Array.from({ length: 10 }, (_, index) => ({
      favcat: index,
      name: "",
    }));
  }
  if (!favoriteOptions.value.some((option) => option.value === favTarget.value)) {
    favTarget.value = favoriteOptions.value[0]?.value ?? "0";
  }
}

async function submitBatchFavorite(): Promise<void> {
  if (busy.value) return;
  const withGid = props.selected.filter(
    (item) => typeof item.gid === "number" && item.gid > 0,
  );
  const skipped = props.selected.length - withGid.length;
  if (!withGid.length) {
    ui.error(t("libraryManage.gidMissing"));
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const result = await addGalleriesToFavorites(
      withGid.map((item) => ({
        gid: item.gid as number,
        token: item.token ?? "",
        title: item.title,
      })),
      Number(favTarget.value) || 0,
    );
    ui.success(
      t("libraryManage.batchFavoriteDone", {
        added: result.successful_gids.length || result.local_added,
        failed: result.cloud_failed.length + skipped,
      }),
    );
    if (skipped) ui.info(t("libraryManage.batchFavoriteNoGid", { count: skipped }));
    favOpen.value = false;
    if (!result.cloud_failed.length && !skipped) emit("clear");
    emit("favorited", result.successful_gids);
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="manage" data-testid="library-manage">
    <SelectionBar
      :count="selectedCount"
      :label="t('libraryManage.selected', { count: selectedCount })"
      @clear="emit('clear')"
    >
      <Button variant="outlined" icon="favorite" data-testid="batch-favorite" @click="openBatchFavorite">
        {{ t("libraryManage.batchFavorite") }}
      </Button>
      <Button variant="outlined" icon="series" data-testid="add-to-list" @click="openAddToList">
        {{ t("libraryManage.listAdd") }}
      </Button>
      <template #danger>
        <Button variant="text" danger icon="delete" data-testid="batch-delete" @click="openBatchDelete">
          {{ t("libraryManage.deleteSelected") }}
        </Button>
      </template>
    </SelectionBar>
    <!-- Legacy e2e hook (`selection-count`): the readable count lives in the
         SelectionBar label; this duplicate is intentionally not painted. -->
    <span class="manage__count" data-testid="selection-count">{{ selectedCount }}</span>

    <Dialog
      :open="addListOpen"
      :title="t('libraryManage.listAddTitle')"
      testid="add-list-dialog"
      @close="addListOpen = false"
    >
      <div class="manage__form">
        <p class="manage__hint">
          {{ t("libraryManage.selected", { count: selectedCount }) }}
        </p>
        <Select
          :model-value="addListTarget"
          :options="targetListOptions"
          :label="t('libraryManage.listAddTarget')"
          @update:model-value="addListTarget = $event"
        />
        <Input
          v-model="addListNewName"
          :label="t('libraryManage.listAddNew')"
          :placeholder="t('libraryManage.listNamePlaceholder')"
        />
        <p v-if="error" class="manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="addListOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          :disabled="busy"
          :loading="busy"
          data-testid="add-list-submit"
          @click="submitAddToList"
        >
          {{ t("libraryManage.listAdd") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="deleteOpen"
      :title="deleteStep === 1 ? t('libraryManage.deleteSelectedTitle') : t('libraryManage.deleteFinalTitle')"
      testid="batch-delete-dialog"
      @close="deleteOpen = false"
    >
      <div class="manage__form">
        <p v-if="deleteStep === 1" class="manage__hint">
          {{ t("libraryManage.deleteSelectedBody", { count: selectedCount }) }}
        </p>
        <p v-else class="manage__warning">
          {{ t("libraryManage.deleteFinalBody", { count: selectedCount }) }}
        </p>
        <label class="manage__switch">
          <Switch v-model="deleteFiles" :label="t('libraryManage.deleteFilesToggle')" />
          <span>{{ t("libraryManage.deleteFilesToggle") }}</span>
        </label>
        <p class="manage__hint">{{ t("libraryManage.deleteFilesHint") }}</p>
        <p v-if="error" class="manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="deleteOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          variant="filled"
          danger
          :loading="busy"
          data-testid="batch-delete-confirm"
          @click="confirmBatchDelete"
        >
          {{ deleteStep === 1 ? t("libraryManage.confirm") : t("libraryManage.deleteConfirm") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="favOpen"
      :title="t('libraryManage.batchFavoriteTitle')"
      testid="batch-favorite-dialog"
      @close="favOpen = false"
    >
      <div class="manage__form">
        <p class="manage__hint">
          {{ t("libraryManage.selected", { count: selectedCount }) }}
        </p>
        <Select
          :model-value="favTarget"
          :options="favoriteOptions"
          :label="t('libraryManage.batchFavoriteTarget')"
          data-testid="batch-favorite-target"
          @update:model-value="favTarget = $event"
        />
        <p class="manage__hint">{{ t("libraryManage.batchFavoriteHint") }}</p>
        <p v-if="error" class="manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="favOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          :disabled="busy"
          :loading="busy"
          data-testid="batch-favorite-submit"
          @click="submitBatchFavorite"
        >
          {{ t("libraryManage.confirm") }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.manage {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

/* Legacy hook, kept out of the visual flow: the SelectionBar shows the count. */
.manage__count {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.manage__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.manage__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.manage__warning {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-medium);
}

.manage__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.manage__switch {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}
</style>
