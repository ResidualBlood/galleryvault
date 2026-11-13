<script setup lang="ts">
/**
 * Saved-search + list creation row for the library filter panel.
 *
 * It was extracted from the old always-visible management block (audit LB-02 /
 * LB-04): the row only exists while the filter panel is open, every control is
 * one control-ladder step (lg / 40), and the apply / delete pair became a text
 * button plus an icon button so the row no longer mixes 32px and 48px boxes.
 *
 * Business behaviour is unchanged: the saved query stores the same
 * `GET /api/galleries` parameters (sizes are written back in MB), applying a
 * saved search navigates to `library` with its query, and creating a list
 * notifies the page so list filters / targets refresh.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import { ApiError } from "@/api/client";
import {
  createSavedSearch,
  deleteSavedSearch,
  fetchSavedSearches,
  type GalleryQuery,
  type SavedSearch,
} from "@/api/library";
import { createList } from "@/api/lists";
import { buildGalleryQuery } from "@/stores/library";
import { useUiStore } from "@/stores/ui";
import { ensureLibraryManageMessages } from "./messages";

ensureLibraryManageMessages();

const props = defineProps<{ query: GalleryQuery }>();
const emit = defineEmits<{ "lists-changed": [] }>();

const { t } = useI18n();
const router = useRouter();
const ui = useUiStore();

const savedSearches = ref<SavedSearch[]>([]);
const selectedSearch = ref("");
const busy = ref(false);
const error = ref("");

const savedSearchOptions = computed(() => [
  {
    value: "",
    label: savedSearches.value.length
      ? t("libraryManage.searchSaved")
      : t("libraryManage.noSavedSearches"),
  },
  ...savedSearches.value.map((item) => ({ value: item.id, label: item.name })),
]);

function message(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

async function loadSavedSearches(): Promise<void> {
  try {
    savedSearches.value = await fetchSavedSearches();
  } catch {
    savedSearches.value = [];
  }
}

onMounted(() => void loadSavedSearches());

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
    // The list store holds API bytes; the library route (and legacy saved
    // searches) use MB, so convert before persisting to avoid double scaling
    // when the saved search is applied again.
    for (const key of ["size_min", "size_max"] as const) {
      const bytes = Number(query[key]);
      if (query[key] && Number.isFinite(bytes)) {
        query[key] = String(Number((bytes / 1048576).toFixed(3)));
      }
    }
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

const newListOpen = ref(false);
const newListName = ref("");

function openNewList(): void {
  newListName.value = "";
  error.value = "";
  newListOpen.value = true;
}

async function submitNewList(): Promise<void> {
  const name = newListName.value.trim();
  if (!name || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await createList(name);
    ui.success(t("libraryManage.listCreated"));
    newListOpen.value = false;
    emit("lists-changed");
  } catch (cause) {
    error.value = message(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="save-bar" data-testid="library-save-bar">
    <Button variant="outlined" data-testid="save-search-open" @click="openSaveSearch">
      {{ t("libraryManage.saveSearch") }}
    </Button>
    <Select
      class="save-bar__select"
      data-testid="saved-search-select"
      :model-value="selectedSearch"
      :options="savedSearchOptions"
      :aria-label="t('libraryManage.savedSearches')"
      @update:model-value="selectedSearch = $event"
    />
    <Button
      variant="text"
      :disabled="!selectedSearch"
      data-testid="apply-search"
      @click="applySavedSearch"
    >
      {{ t("libraryManage.applySearch") }}
    </Button>
    <IconButton
      name="delete"
      :label="t('libraryManage.deleteSearch')"
      :disabled="!selectedSearch"
      data-testid="delete-search"
      @click="removeSavedSearch"
    />
    <Button variant="outlined" data-testid="new-list" @click="openNewList">
      {{ t("libraryManage.listNew") }}
    </Button>

    <Dialog
      :open="saveSearchOpen"
      :title="t('libraryManage.saveSearchTitle')"
      testid="save-search-dialog"
      @close="saveSearchOpen = false"
    >
      <div class="save-bar__form">
        <p class="save-bar__hint">{{ t("libraryManage.saveSearchHint") }}</p>
        <Input
          v-model="saveSearchName"
          :label="t('libraryManage.saveSearchName')"
          :placeholder="t('libraryManage.saveSearchPlaceholder')"
          data-testid="save-search-name"
          @enter="submitSaveSearch"
        />
        <p v-if="error" class="save-bar__error">{{ error }}</p>
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

    <Dialog
      :open="newListOpen"
      :title="t('libraryManage.listNewTitle')"
      testid="new-list-dialog"
      @close="newListOpen = false"
    >
      <div class="save-bar__form">
        <Input
          v-model="newListName"
          :label="t('libraryManage.listName')"
          :placeholder="t('libraryManage.listNamePlaceholder')"
          data-testid="new-list-name"
          @enter="submitNewList"
        />
        <p v-if="error" class="save-bar__error">{{ error }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="newListOpen = false">
          {{ t("libraryManage.cancel") }}
        </Button>
        <Button
          :disabled="!newListName.trim() || busy"
          :loading="busy"
          data-testid="new-list-submit"
          @click="submitNewList"
        >
          {{ t("libraryManage.save") }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.save-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.save-bar__select {
  flex: none;
  width: 220px;
}

.save-bar__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.save-bar__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.save-bar__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

@media (max-width: 599.98px) {
  .save-bar__select {
    width: 100%;
  }
}
</style>
