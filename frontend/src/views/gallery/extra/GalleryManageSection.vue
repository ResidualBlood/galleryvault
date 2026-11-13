<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import TextArea from "@/components/ui/TextArea.vue";
import { ApiError } from "@/api/client";
import {
  deleteGallery,
  downloadGalleryOriginal,
  galleryExportCbzUrl,
  getGalleryFavorite,
  patchGalleryLocal,
  redownloadGallery,
  setGalleryFavoriteNote,
  type GalleryDetail,
} from "@/api/gallery";
import { fetchGalleryLists, fetchLists, addListItems, removeListItems, type GalleryList } from "@/api/lists";
import { syncGalleryTags } from "@/api/tags";
import { useUiStore } from "@/stores/ui";
import { ensureLibraryManageMessages } from "@/views/library/manage/messages";

ensureLibraryManageMessages();

const props = defineProps<{ gallery: GalleryDetail }>();
const emit = defineEmits<{ refresh: [] }>();

const { t } = useI18n();
const router = useRouter();
const ui = useUiStore();

const busy = ref(false);

/* --------------------------------------------------------------- local data */

const rating = ref("");
const localTags = ref("");
const localNote = ref("");
const localError = ref("");

const ratingOptions = computed(() => [
  { value: "", label: "—" },
  ...[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: String(value) })),
]);

function syncLocalFields(gallery: GalleryDetail): void {
  rating.value =
    typeof gallery.local_rating === "number" ? String(gallery.local_rating) : "";
  localTags.value = (gallery.tags ?? [])
    .filter((tag) => tag.namespace === "local")
    .map((tag) => tag.name)
    .join(", ");
  localNote.value = gallery.local_note ?? "";
  localError.value = "";
}

watch(
  () => props.gallery.id,
  () => syncLocalFields(props.gallery),
  { immediate: true },
);

function message(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof Error) return cause.message;
  return String(cause);
}

async function saveLocal(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  localError.value = "";
  try {
    await patchGalleryLocal(props.gallery.id, {
      local_rating: rating.value ? Number(rating.value) : null,
      local_note: localNote.value,
      local_tags: localTags.value
        .split(/[,，]/)
        .map((value) => value.trim())
        .filter(Boolean),
    });
    ui.success(t("legacy.saveLocal"));
    emit("refresh");
  } catch (cause) {
    localError.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* -------------------------------------------------------------------- lists */

const allLists = ref<GalleryList[]>([]);
const mine = ref<Set<number>>(new Set());
const listsError = ref("");

async function loadLists(): Promise<void> {
  try {
    const [all, own] = await Promise.all([
      fetchLists(),
      fetchGalleryLists(props.gallery.id),
    ]);
    allLists.value = all;
    mine.value = new Set(own.map((item) => item.id));
    listsError.value = "";
  } catch (cause) {
    listsError.value = message(cause);
  }
}

watch(
  () => props.gallery.id,
  () => {
    void loadLists();
  },
  { immediate: true },
);

async function toggleList(list: GalleryList, inList: boolean): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    if (inList) await removeListItems(list.id, [props.gallery.id]);
    else await addListItems(list.id, [props.gallery.id]);
    await loadLists();
  } catch (cause) {
    listsError.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* ------------------------------------------------------------ favourite note */

const favNote = ref("");
const favLoaded = ref(false);
const favError = ref("");
const favcats = ref<number[]>([]);

const noteEnabled = computed(() => Boolean(props.gallery.gid));

async function loadFavourite(): Promise<void> {
  if (!props.gallery.gid) return;
  try {
    const info = await getGalleryFavorite(props.gallery.id);
    favNote.value = info.note ?? "";
    favcats.value = info.favcats ?? [];
    favLoaded.value = true;
  } catch {
    favLoaded.value = false;
  }
}

watch(
  () => props.gallery.id,
  () => {
    favLoaded.value = false;
    favNote.value = "";
    void loadFavourite();
  },
  { immediate: true },
);

async function saveNote(): Promise<void> {
  if (busy.value || !props.gallery.gid) return;
  busy.value = true;
  favError.value = "";
  try {
    const result = await setGalleryFavoriteNote({
      gid: props.gallery.gid,
      token: props.gallery.token ?? "",
      favcat: favcats.value[0] ?? props.gallery.favorite_category ?? 0,
      note: favNote.value,
    });
    if (result.cloud_ok) ui.success(t("legacy.saveFavNote"));
    else ui.error(t("legacy.favAddFail"));
    emit("refresh");
  } catch (cause) {
    favError.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* ------------------------------------------------------------------ actions */

async function syncTags(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    const result = await syncGalleryTags(props.gallery.id);
    ui.success(
      result.source === "cache"
        ? t("legacy.tagSyncFromCache")
        : `${t("legacy.tagSyncFromNetwork")}${result.count ? ` · ${result.count}` : ""}`,
    );
    emit("refresh");
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}

async function redownload(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    await redownloadGallery(props.gallery.id);
    ui.success(t("libraryManage.redownloadQueued"));
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}

async function downloadOriginal(archive: boolean): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    await downloadGalleryOriginal(props.gallery.id, archive);
    ui.success(t(archive ? "legacy.dlOrigArchiveQueued" : "legacy.dlOrigQueued"));
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}

const deleteOpen = ref(false);
const deleteFiles = ref(false);
const deleteError = ref("");

function openDelete(): void {
  deleteFiles.value = false;
  deleteError.value = "";
  deleteOpen.value = true;
}

async function confirmDelete(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  deleteError.value = "";
  try {
    await deleteGallery(props.gallery.id, deleteFiles.value);
    ui.success(t("legacy.deleted"));
    deleteOpen.value = false;
    await router.push({ name: "library" });
  } catch (cause) {
    deleteError.value = message(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="manage" data-testid="gallery-manage">
    <div class="manage__head">
      <h2 class="manage__title">{{ t("legacy.more") }}</h2>
      <div class="manage__actions" data-gv-toolbar="manage-actions">
        <Button
          variant="tonal"
          size="sm"
          icon="downloads"
          data-testid="redownload"
          :loading="busy"
          @click="redownload"
        >
          {{ t("libraryManage.redownload") }}
        </Button>
        <a
          class="manage__link"
          data-testid="export-cbz"
          :href="galleryExportCbzUrl(gallery.id)"
          download
        >
          {{ t("legacy.exportCbz") }}
        </a>
        <Button
          variant="outlined"
          size="sm"
          icon="retry"
          data-testid="sync-tags"
          :loading="busy"
          @click="syncTags"
        >
          {{ t("legacy.syncTags") }}
        </Button>
        <Button
          v-if="gallery.gid"
          variant="outlined"
          size="sm"
          data-testid="download-original"
          :loading="busy"
          @click="downloadOriginal(false)"
        >
          {{ t("legacy.dlOrig") }}
        </Button>
        <Button
          v-if="gallery.gid"
          variant="outlined"
          size="sm"
          data-testid="download-original-archive"
          :loading="busy"
          @click="downloadOriginal(true)"
        >
          {{ t("legacy.dlOrigArchive") }}
        </Button>
      </div>
    </div>

    <div class="manage__grid">
      <section class="card" data-testid="local-fields">
        <div class="card__row">
          <Select
            class="card__select"
            :model-value="rating"
            :options="ratingOptions"
            :label="t('legacy.localRating')"
            @update:model-value="rating = $event"
          />
        </div>
        <Input
          v-model="localTags"
          :label="t('legacy.localTags')"
          :placeholder="t('legacy.localTags')"
          data-testid="local-tags"
        />
        <TextArea
          v-model="localNote"
          :label="t('legacy.localNote')"
          :placeholder="t('legacy.localNote')"
          :rows="3"
          data-testid="local-note"
        />
        <p v-if="localError" class="card__error">{{ localError }}</p>
        <Button
          variant="filled"
          size="compact"
          :loading="busy"
          data-testid="save-local"
          @click="saveLocal"
        >
          {{ t("legacy.saveLocal") }}
        </Button>
      </section>

      <section class="card" data-testid="gallery-lists">
        <h3 class="card__title">{{ t("legacy.galleryLists") }}</h3>
        <p v-if="listsError" class="card__error">{{ listsError }}</p>
        <p v-if="!allLists.length" class="card__hint">{{ t("legacy.galleryLists") }}</p>
        <div class="card__chips">
          <Button
            v-for="list in allLists"
            :key="list.id"
            class="card__chip"
            :variant="mine.has(list.id) ? 'tonal' : 'outlined'"
            size="sm"
            :disabled="busy"
            :data-testid="`list-toggle-${list.id}`"
            @click="toggleList(list, mine.has(list.id))"
          >
            <span class="card__chip-label">
              {{ mine.has(list.id) ? t("legacy.listRemove") : t("legacy.listAdd") }}
            </span>
            <span class="card__chip-name" :title="list.name">{{ list.name }}</span>
          </Button>
        </div>
      </section>

      <section class="card" data-testid="favorite-note">
        <p v-if="!noteEnabled" class="card__hint">{{ t("legacy.galleryLists") }}</p>
        <template v-else>
          <Input
            v-model="favNote"
            :label="t('legacy.favNote')"
            :placeholder="t('legacy.favNote')"
            data-testid="fav-note"
          />
          <p v-if="favError" class="card__error">{{ favError }}</p>
          <Button
            variant="outlined"
            size="compact"
            :disabled="busy || !favLoaded"
            data-testid="save-fav-note"
            @click="saveNote"
          >
            {{ t("legacy.saveFavNote") }}
          </Button>
        </template>
      </section>
    </div>

    <div class="manage__footer">
      <Button
        variant="text"
        size="sm"
        danger
        icon="delete"
        data-testid="delete-gallery"
        @click="openDelete"
      >
        {{ t("legacy.deleteGallery") }}
      </Button>
    </div>

    <Dialog
      :open="deleteOpen"
      :title="t('legacy.deleteGallery')"
      testid="delete-gallery-dialog"
      @close="deleteOpen = false"
    >
      <div class="manage__form">
        <p class="card__hint">{{ t("legacy.confirmDelete") }}</p>
        <label class="manage__switch">
          <Switch v-model="deleteFiles" :label="t('legacy.deleteFiles')" />
          <span>{{ t("legacy.deleteFiles") }}</span>
        </label>
        <p v-if="deleteError" class="card__error">{{ deleteError }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="deleteOpen = false">{{ t("legacy.cancel") }}</Button>
        <Button
          variant="filled"
          :loading="busy"
          data-testid="delete-gallery-confirm"
          @click="confirmDelete"
        >
          {{ t("legacy.deleteGallery") }}
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

.manage__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.manage__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.manage__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

/* GD-08: the export entry is a real download link, laid out on the same `sm`
   step as the buttons beside it so the row keeps one height and one baseline. */
.manage__link {
  display: inline-flex;
  align-items: center;
  height: var(--gv-size-control-sm);
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.manage__link:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-hover), transparent);
}

.manage__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.manage__footer {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--gv-space-2);
  border-top: 1px solid var(--gv-color-outline-variant);
}

.manage__grid {
  display: grid;
  gap: var(--gv-space-3);
}

.card {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.card__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
}

.card__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.card__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.card__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.card__select {
  min-width: 120px;
}

/* GD-10: the verb stays in the button label; the list name is a separate
   truncating span so four buttons no longer differ by 10-15px in width. */
.card__chips {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--gv-space-2);
}

.card__chip {
  justify-content: flex-start;
  min-width: 0;
}

.card__chip-label {
  flex: none;
}

.card__chip-name {
  min-width: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manage__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.manage__switch {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}

@media (min-width: 840px) {
  .manage__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
