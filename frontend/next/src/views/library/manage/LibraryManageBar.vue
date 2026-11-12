<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import { ApiError } from "@/api/client";
import {
  addGalleriesToFavorites,
  createSavedSearch,
  deleteGalleriesBulk,
  deleteGalleriesFiltered,
  deleteSavedSearch,
  fetchSavedSearches,
  type FilteredDeletePayload,
  type GalleryItem,
  type GalleryQuery,
  type SavedSearch,
} from "@/api/library";
import { addListItems, createList, fetchLists, type GalleryList } from "@/api/lists";
import { fetchFavoriteCategories, type FavoriteCategory } from "@/api/favorites";
import { buildGalleryQuery } from "@/stores/library";
import { useUiStore } from "@/stores/ui";
import { ensureLibraryManageMessages } from "./messages";

ensureLibraryManageMessages();

const props = defineProps<{
  query: GalleryQuery;
  selected: GalleryItem[];
  /** Total matches for the active filter (used for copy only). */
  total: number;
}>();

const emit = defineEmits<{
  clear: [];
  removed: [ids: number[], deleted: number];
  favorited: [gids: number[]];
}>();

const { t } = useI18n();
const router = useRouter();
const ui = useUiStore();

const savedSearches = ref<SavedSearch[]>([]);
const lists = ref<GalleryList[]>([]);
const favoriteCategories = ref<FavoriteCategory[]>([]);

const selectedSearch = ref("");
const selectedListFilter = ref("");
const busy = ref(false);
const error = ref("");

/* ------------------------------------------------------------ derived state */

const selectedCount = computed(() => props.selected.length);

const savedSearchOptions = computed(() => [
  {
    value: "",
    label: savedSearches.value.length
      ? t("libraryManage.searchSaved")
      : t("libraryManage.noSavedSearches"),
  },
  ...savedSearches.value.map((item) => ({ value: item.id, label: item.name })),
]);

const listFilterOptions = computed(() => [
  { value: "", label: t("libraryManage.listFilterAll") },
  ...lists.value.map((item) => ({
    value: String(item.id),
    label: `${item.name} (${item.count ?? 0})`,
  })),
]);

const targetListOptions = computed(() => [
  { value: "", label: t("libraryManage.listAddTarget") },
  ...lists.value.map((item) => ({
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

/* ------------------------------------------------------------------ loading */

async function loadSavedSearches(): Promise<void> {
  try {
    savedSearches.value = await fetchSavedSearches();
  } catch {
    savedSearches.value = [];
  }
}

async function loadLists(): Promise<void> {
  try {
    lists.value = await fetchLists();
  } catch {
    lists.value = [];
  }
}

onMounted(() => {
  selectedListFilter.value = props.query.list_id ? String(props.query.list_id) : "";
  void loadSavedSearches();
  void loadLists();
});

function message(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

/* -------------------------------------------------------- saved searches */

const saveSearchOpen = ref(false);
const saveSearchName = ref("");

function openSaveSearch(): void {
  saveSearchName.value = "";
  error.value = "";
  saveSearchOpen.value = true;
}

async function submitSaveSearch(): Promise<void> {
  const name = saveSearchName.value.trim();
  if (!name || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const query = buildGalleryQuery(props.query);
    await createSavedSearch(name, query);
    ui.success(t("libraryManage.saveSearch"));
    saveSearchOpen.value = false;
    await loadSavedSearches();
  } catch (cause) {
    const text = message(cause);
    error.value = /limit/i.test(text) ? t("libraryManage.savedSearchLimit") : text;
  } finally {
    busy.value = false;
  }
}

function applySavedSearch(): void {
  const found = savedSearches.value.find((item) => item.id === selectedSearch.value);
  if (!found) return;
  const query: Record<string, string> = {};
  for (const [key, value] of Object.entries(found.query ?? {})) {
    if (value !== "" && value !== null && value !== undefined) query[key] = String(value);
  }
  void router.push({ name: "library", query });
}

async function removeSavedSearch(): Promise<void> {
  if (!selectedSearch.value || busy.value) return;
  busy.value = true;
  try {
    await deleteSavedSearch(selectedSearch.value);
    selectedSearch.value = "";
    await loadSavedSearches();
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}

/* ------------------------------------------------------------------- lists */

const newListOpen = ref(false);
const newListName = ref("");
const addListOpen = ref(false);
const addListTarget = ref("");
const addListNewName = ref("");

function openNewList(): void {
  newListName.value = "";
  error.value = "";
  newListOpen.value = true;
}

async function submitNewList(): Promise<boolean> {
  const name = newListName.value.trim();
  if (!name || busy.value) return false;
  busy.value = true;
  error.value = "";
  try {
    await createList(name);
    ui.success(t("libraryManage.listCreated"));
    newListOpen.value = false;
    await loadLists();
    return true;
  } catch (cause) {
    error.value = message(cause);
    return false;
  } finally {
    busy.value = false;
  }
}

function openAddToList(): void {
  if (!selectedCount.value) {
    ui.info(t("libraryManage.listAddEmpty"));
    return;
  }
  addListTarget.value = props.query.list_id ? String(props.query.list_id) : "";
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
    await loadLists();
    emit("clear");
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}

function onListFilter(value: string): void {
  selectedListFilter.value = value;
  const query: Record<string, string> = {};
  for (const [key, item] of Object.entries(props.query)) {
    if (item === undefined || item === null || item === "") continue;
    query[key] = String(item);
  }
  if (value) query.list_id = value;
  else delete query.list_id;
  delete query.page;
  void router.push({ name: "library", query });
}

async function submitNewListOnly(): Promise<void> {
  const ok = await submitNewList();
  if (ok) {
    selectedListFilter.value = "";
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

/* --------------------------------------------------------- filtered delete */

const filteredOpen = ref(false);
const filteredPhase = ref<"confirm" | "typed">("confirm");
const filteredMatchCount = ref(0);
const filteredConfirmValue = ref("");
const filteredFiles = ref(false);

function openFilteredDelete(): void {
  if (!hasFilters.value) return;
  filteredPhase.value = "confirm";
  filteredMatchCount.value = 0;
  filteredConfirmValue.value = "";
  filteredFiles.value = false;
  error.value = "";
  filteredOpen.value = true;
}

const typedMismatch = computed(
  () =>
    filteredPhase.value === "typed" &&
    filteredConfirmValue.value.trim() !== "" &&
    filteredConfirmValue.value.trim() !== String(filteredMatchCount.value),
);

async function runFilteredDelete(payload: FilteredDeletePayload): Promise<void> {
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
    filteredOpen.value = false;
    emit("clear");
    // Legacy resets to the unfiltered library after a filtered delete; the new
    // query key makes the list store fetch the remaining galleries.
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
      filteredMatchCount.value = Number.isFinite(matched) ? matched : 0;
      filteredPhase.value = "typed";
      filteredConfirmValue.value = "";
      return;
    }
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}

async function submitFilteredDelete(): Promise<void> {
  if (busy.value) return;
  if (filteredPhase.value === "confirm") {
    await runFilteredDelete({ delete_files: filteredFiles.value });
    return;
  }
  if (filteredConfirmValue.value.trim() !== String(filteredMatchCount.value)) return;
  await runFilteredDelete({
    delete_files: filteredFiles.value,
    confirm: true,
    match_count: filteredMatchCount.value,
  });
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
  <section class="manage" data-testid="library-manage">
    <div class="manage__row">
      <Button
        variant="outlined"
        size="compact"
        data-testid="save-search-open"
        @click="openSaveSearch"
      >
        {{ t("libraryManage.saveSearch") }}
      </Button>
      <Select
        class="manage__select"
        data-testid="saved-search-select"
        :model-value="selectedSearch"
        :options="savedSearchOptions"
        :label="t('libraryManage.savedSearches')"
        @update:model-value="selectedSearch = $event"
      />
      <Button
        variant="text"
        size="compact"
        :disabled="!selectedSearch"
        data-testid="apply-search"
        @click="applySavedSearch"
      >
        {{ t("libraryManage.applySearch") }}
      </Button>
      <Button
        variant="text"
        size="compact"
        :disabled="!selectedSearch"
        data-testid="delete-search"
        @click="removeSavedSearch"
      >
        {{ t("libraryManage.deleteSearch") }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        data-testid="new-list"
        @click="openNewList"
      >
        {{ t("libraryManage.listNew") }}
      </Button>
      <Select
        class="manage__select manage__select--list"
        data-testid="list-filter"
        :model-value="selectedListFilter"
        :options="listFilterOptions"
        :label="t('libraryManage.listFilter')"
        @update:model-value="onListFilter"
      />
    </div>

    <div class="manage__row manage__row--actions">
      <span class="manage__count" data-testid="selection-count">
        {{ t("libraryManage.selected", { count: selectedCount }) }}
      </span>
      <Button
        variant="text"
        size="compact"
        :disabled="!selectedCount"
        data-testid="clear-selection"
        @click="emit('clear')"
      >
        {{ t("libraryManage.clearSelection") }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        :disabled="!selectedCount"
        data-testid="batch-favorite"
        @click="openBatchFavorite"
      >
        {{ t("libraryManage.batchFavorite") }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        :disabled="!selectedCount"
        data-testid="add-to-list"
        @click="openAddToList"
      >
        {{ t("libraryManage.listAdd") }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        :disabled="!selectedCount"
        data-testid="batch-delete"
        @click="openBatchDelete"
      >
        {{ t("libraryManage.deleteSelected") }}
      </Button>
      <Button
        variant="text"
        size="compact"
        :disabled="!hasFilters"
        data-testid="filtered-delete"
        :title="hasFilters ? filterSummary : t('libraryManage.filteredDeleteEmpty')"
        @click="openFilteredDelete"
      >
        {{ t("libraryManage.filteredDelete") }}
      </Button>
    </div>

    <!-- Save current search -->
    <Dialog
      :open="saveSearchOpen"
      :title="t('libraryManage.saveSearchTitle')"
      testid="save-search-dialog"
      @close="saveSearchOpen = false"
    >
      <div class="manage__form">
        <p class="manage__hint">{{ t("libraryManage.saveSearchHint") }}</p>
        <Input
          v-model="saveSearchName"
          :label="t('libraryManage.saveSearchName')"
          :placeholder="t('libraryManage.saveSearchPlaceholder')"
          data-testid="save-search-name"
          @enter="submitSaveSearch"
        />
        <p v-if="error" class="manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="saveSearchOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          :disabled="!saveSearchName.trim() || busy"
          :loading="busy"
          data-testid="save-search-submit"
          @click="submitSaveSearch"
        >
          {{ t("libraryManage.save") }}
        </Button>
      </template>
    </Dialog>

    <!-- New list -->
    <Dialog
      :open="newListOpen"
      :title="t('libraryManage.listNewTitle')"
      testid="new-list-dialog"
      @close="newListOpen = false"
    >
      <div class="manage__form">
        <Input
          v-model="newListName"
          :label="t('libraryManage.listName')"
          :placeholder="t('libraryManage.listNamePlaceholder')"
          data-testid="new-list-name"
          @enter="submitNewListOnly"
        />
        <p v-if="error" class="manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="newListOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          :disabled="!newListName.trim() || busy"
          :loading="busy"
          data-testid="new-list-submit"
          @click="submitNewListOnly"
        >
          {{ t("libraryManage.save") }}
        </Button>
      </template>
    </Dialog>

    <!-- Add selection to a list -->
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

    <!-- Batch delete: two steps -->
    <Dialog
      :open="deleteOpen"
      :title="deleteStep === 1 ? t('libraryManage.deleteSelectedTitle') : t('libraryManage.deleteFinalTitle')"
      testid="batch-delete-dialog"
      @close="deleteOpen = false"
    >
      <div class="manage__form">
        <p class="manage__hint" v-if="deleteStep === 1">
          {{ t("libraryManage.deleteSelectedBody", { count: selectedCount }) }}
        </p>
        <p class="manage__warning" v-else>
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
          :loading="busy"
          data-testid="batch-delete-confirm"
          @click="confirmBatchDelete"
        >
          {{ deleteStep === 1 ? t("libraryManage.confirm") : t("libraryManage.deleteConfirm") }}
        </Button>
      </template>
    </Dialog>

    <!-- Filtered delete: confirm, then type the match count for large sets -->
    <Dialog
      :open="filteredOpen"
      :title="filteredPhase === 'confirm' ? t('libraryManage.filteredDeleteTitle') : t('libraryManage.filteredDeleteLargeTitle')"
      testid="filtered-delete-dialog"
      @close="filteredOpen = false"
    >
      <div class="manage__form">
        <p class="manage__hint">
          {{ t("libraryManage.filteredDeleteSummary", { summary: filterSummary }) }}
        </p>
        <p v-if="filteredPhase === 'confirm'" class="manage__hint">
          {{ t("libraryManage.filteredDeleteBody") }}
        </p>
        <p v-else class="manage__warning">
          {{ t("libraryManage.filteredDeleteLargeBody", { count: filteredMatchCount }) }}
        </p>
        <label class="manage__switch">
          <Switch v-model="filteredFiles" :label="t('libraryManage.deleteFilesToggle')" />
          <span>{{ t("libraryManage.deleteFilesToggle") }}</span>
        </label>
        <p class="manage__hint">{{ t("libraryManage.deleteFilesHint") }}</p>
        <Input
          v-if="filteredPhase === 'typed'"
          v-model="filteredConfirmValue"
          :label="t('libraryManage.filteredDeleteTypeHint', { count: filteredMatchCount })"
          :error="typedMismatch ? t('libraryManage.filteredDeleteMismatch') : ''"
          data-testid="filtered-delete-count"
          @enter="submitFilteredDelete"
        />
        <p v-if="error" class="manage__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="filteredOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          variant="filled"
          :disabled="filteredPhase === 'typed' && filteredConfirmValue.trim() !== String(filteredMatchCount)"
          :loading="busy"
          data-testid="filtered-delete-confirm"
          @click="submitFilteredDelete"
        >
          {{ t("libraryManage.deleteConfirm") }}
        </Button>
      </template>
    </Dialog>

    <!-- Batch favourite -->
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
  </section>
</template>

<style scoped>
.manage {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
}

.manage__row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.manage__row--actions {
  align-items: center;
  padding-top: var(--gv-space-2);
  border-top: 1px solid var(--gv-color-outline-variant);
}

.manage__select {
  min-width: 180px;
}

.manage__select--list {
  min-width: 160px;
}

.manage__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
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
