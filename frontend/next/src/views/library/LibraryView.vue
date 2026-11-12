<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import TagSuggest from "./TagSuggest.vue";
import VirtualGrid from "@/components/gallery/VirtualGrid.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import LibraryManageBar from "./manage/LibraryManageBar.vue";
import { useGallerySelection } from "./manage/useSelection";
import { ensureLibraryManageMessages } from "./manage/messages";
import { ensureLibraryMessages } from "./messages";
import {
  clampPageSize,
  PAGE_SIZES,
  useLibraryStore,
} from "@/stores/library";
import type { GalleryQuery, TagSuggestion } from "@/api/library";
import { useSettingsStore } from "@/stores/settings";

ensureLibraryMessages();
ensureLibraryManageMessages();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useLibraryStore();
const settings = useSettingsStore();
const selection = useGallerySelection();

const selectedItems = computed(() => store.items.filter((item) => selection.has(item.id)));
const manageQuery = computed(() => store.currentQuery);

function toggleSelected(id: number, event: Event): void {
  selection.toggle(id, (event.target as HTMLInputElement).checked);
}

/** Drop deleted rows locally; the server already confirmed the deletion. */
function onRemoved(ids: number[], deleted: number): void {
  const removed = new Set(ids);
  store.items = store.items.filter((item) => !removed.has(item.id));
  store.total = Math.max(0, store.total - deleted);
}

/** Reflect cloud-confirmed favourites on the visible cards. */
function onFavorited(gids: number[]): void {
  const added = new Set(gids);
  for (const item of store.items) {
    if (item.gid && added.has(item.gid)) item.favorite = true;
  }
}

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

const term = ref("");
const tags = ref("");
const category = ref("");
const orderBy = ref("id_desc");
const readStatus = ref("");
const pageSize = ref(settings.pageSize);

const activeTags = computed(() =>
  tags.value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean),
);

const pageSizeOptions = computed(() => {
  const values = new Set(PAGE_SIZES.map(String));
  values.add(String(pageSize.value));
  return [...values]
    .map(Number)
    .sort((a, b) => a - b)
    .map((value) => ({ value: String(value), label: String(value) }));
});

const categoryOptions = computed(() => [
  { value: "", label: t("legacy.allCategories") },
  ...["doujinshi", "manga", "artistcg", "gamecg", "western", "non-h", "image_set", "cosplay", "asianporn", "misc", "deleted"].map(
    (value) => ({ value, label: categoryLabel(value) }),
  ),
]);

const orderOptions = computed(() => [
  { value: "id_desc", label: t("legacy.orderDefault") },
  { value: "posted_at_desc", label: t("legacy.orderPosted") },
  { value: "title_asc", label: t("legacy.orderTitle") },
  { value: "page_count_desc", label: t("legacy.orderPages") },
  { value: "file_size_desc", label: t("legacy.orderSize") },
  { value: "rating_desc", label: t("legacy.orderRating") },
]);

const readStatusOptions = computed(() => [
  { value: "", label: t("legacy.readStatusAll") },
  { value: "unread", label: t("legacy.readStatusUnread") },
  { value: "reading", label: t("legacy.readStatusReading") },
  { value: "completed", label: t("legacy.readStatusCompleted") },
]);

const totalLabel = computed(() => t("library.page.totalBooks", { n: store.total }));

function categoryLabel(value: string): string {
  const keys: Record<string, string> = {
    doujinshi: "catDoujinshi",
    manga: "catManga",
    artistcg: "catArtistcg",
    gamecg: "catGamecg",
    western: "catWestern",
    "non-h": "catNonH",
    image_set: "catImageSet",
    cosplay: "catCosplay",
    asianporn: "catAsianporn",
    misc: "catMisc",
    deleted: "catDeleted",
  };
  return t(`legacy.${keys[value] ?? "catMisc"}`);
}

function syncFromRoute(): void {
  term.value = first(route.query.q);
  tags.value = first(route.query.tags);
  category.value = first(route.query.category);
  orderBy.value = first(route.query.order_by) || "id_desc";
  readStatus.value = first(route.query.read_status);
  pageSize.value = clampPageSize(
    first(route.query.page_size) || settings.pageSize,
    settings.pageSize,
  );

  const query: GalleryQuery = {
    q: term.value.trim(),
    tags: tags.value,
    category: category.value,
    order_by: orderBy.value,
    read_status: readStatus.value,
    page_size: pageSize.value,
  };
  store.start(query, settings.pageSize);
  restoreScrollSoon();
}

function pushQuery(patch: Record<string, string> = {}): void {
  const merged: Record<string, string> = {
    q: term.value.trim(),
    tags: tags.value,
    category: category.value,
    order_by: orderBy.value,
    read_status: readStatus.value,
    page_size: String(pageSize.value),
    ...patch,
  };
  const query: Record<string, string> = {};
  for (const [key, value] of Object.entries(merged)) {
    if (value) query[key] = value;
  }
  void router.push({ name: "library", query });
}

function onSearch(): void {
  pushQuery({ q: term.value.trim() });
}

function onSelectTag(tag: TagSuggestion): void {
  const key = tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name;
  const current = activeTags.value;
  const next = current.includes(key) ? current : [...current, key];
  term.value = "";
  tags.value = next.join(",");
  pushQuery({ q: "", tags: tags.value });
}

function removeTag(tag: string): void {
  tags.value = activeTags.value.filter((item) => item !== tag).join(",");
  pushQuery({ tags: tags.value });
}

function clearFilters(): void {
  term.value = "";
  tags.value = "";
  category.value = "";
  readStatus.value = "";
  orderBy.value = "id_desc";
  pushQuery({
    q: "",
    tags: "",
    category: "",
    read_status: "",
    order_by: "id_desc",
  });
}

function onPageSize(value: string): void {
  const next = clampPageSize(value, settings.pageSize);
  pageSize.value = next;
  settings.setPageSize(next);
  pushQuery({ page_size: String(next) });
}

function restoreScrollSoon(): void {
  if (!store.items.length) return;
  const target = store.savedScroll();
  if (target <= 0) return;
  void nextTick(() => {
    window.requestAnimationFrame(() => {
      window.scrollTo(0, target);
    });
  });
}

watch(
  () => route.query,
  () => {
    selection.clear();
    syncFromRoute();
  },
  { deep: true },
);

onMounted(() => {
  syncFromRoute();
});

onBeforeRouteLeave(() => {
  store.saveScroll(window.scrollY);
});

onBeforeUnmount(() => {
  store.saveScroll(window.scrollY);
});
</script>

<template>
  <section class="library" data-testid="library-view">
    <header class="library__header">
      <p class="library__eyebrow">{{ t("library.page.eyebrow") }}</p>
      <div class="library__heading">
        <h1 class="library__title">{{ t("library.page.title") }}</h1>
        <span class="library__total">{{ totalLabel }}</span>
      </div>
    </header>

    <form class="library__toolbar" role="search" @submit.prevent="onSearch">
      <TagSuggest
        v-model="term"
        :label="t('library.page.search')"
        :placeholder="t('library.page.searchPlaceholder')"
        @select="onSelectTag"
      />
      <Button type="submit" variant="filled">{{ t("library.page.search") }}</Button>
      <Button type="button" variant="outlined" @click="clearFilters">
        {{ t("library.page.clearFilters") }}
      </Button>
    </form>

    <div class="library__filters">
      <Select
        class="library__select"
        :model-value="category"
        :options="categoryOptions"
        :label="t('library.page.categoryLabel')"
        @update:model-value="category = $event; pushQuery({ category: $event })"
      />
      <Select
        class="library__select"
        :model-value="readStatus"
        :options="readStatusOptions"
        :label="t('library.page.readStatusLabel')"
        @update:model-value="readStatus = $event; pushQuery({ read_status: $event })"
      />
      <Select
        class="library__select"
        data-testid="order-select"
        :model-value="orderBy"
        :options="orderOptions"
        :label="t('library.page.orderLabel')"
        @update:model-value="orderBy = $event; pushQuery({ order_by: $event })"
      />
      <Select
        class="library__select library__select--size"
        data-testid="page-size-select"
        :model-value="String(pageSize)"
        :options="pageSizeOptions"
        :label="t('library.page.pageSizeLabel')"
        @update:model-value="onPageSize"
      />
    </div>

    <LibraryManageBar
      :query="manageQuery"
      :selected="selectedItems"
      :total="store.total"
      @clear="selection.clear()"
      @removed="onRemoved"
      @favorited="onFavorited"
    />

    <div v-if="activeTags.length" class="library__tags" :aria-label="t('library.page.activeTagsLabel')">
      <span v-for="tag in activeTags" :key="tag" class="library__tag">
        {{ tag }}
        <button
          type="button"
          class="library__tag-remove"
          :aria-label="`${t('library.page.removeTag')} ${tag}`"
          @click="removeTag(tag)"
        >
          ×
        </button>
      </span>
    </div>

    <div v-if="store.initialLoading" class="library__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 12" :key="index" variant="card" />
    </div>

    <ErrorState
      v-else-if="store.error && store.items.length === 0"
      :title="t('common.errorTitle')"
      :body="store.error"
      :retry-label="t('common.retry')"
      @retry="store.retry"
    />

    <EmptyState
      v-else-if="!store.items.length"
      :title="t('library.page.emptyTitle')"
      :body="t('library.page.emptyBody')"
      testid="library-empty"
    />

    <VirtualGrid
      v-else
      :items="store.items"
      :loading="store.loading"
      :has-more="store.hasMore"
      :error="store.error"
      :failures="store.failures"
      :total="store.total"
      data-testid="library-grid"
      @load-more="store.loadMore"
      @retry="store.retry"
    >
      <template #card="{ item }">
        <div
          class="library-card"
          :class="{ 'library-card--selected': selection.has(item.id) }"
          data-testid="library-card"
        >
          <label class="library-card__check" :title="t('libraryManage.select')">
            <input
              type="checkbox"
              :checked="selection.has(item.id)"
              :aria-label="`${t('libraryManage.select')} ${item.title}`"
              @change="toggleSelected(item.id, $event)"
            />
          </label>
          <GalleryCard :item="item" />
        </div>
      </template>
    </VirtualGrid>
  </section>
</template>

<style scoped>
.library {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.library__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.library__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.library__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--gv-space-3);
}

.library__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.library__total {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.library__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.library__filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-3);
}

.library__select {
  min-width: 160px;
}

.library__select--size {
  min-width: 120px;
}

.library__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.library__tag {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: 24px;
  padding: 0 var(--gv-space-1) 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
}

.library__tag-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: inherit;
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.library__tag-remove:hover {
  background: var(--gv-color-surface-container-highest);
}

.library-card {
  position: relative;
}

.library-card--selected {
  outline: 2px solid var(--gv-color-primary);
  outline-offset: 2px;
  border-radius: var(--gv-radius-md);
}

.library-card__check {
  position: absolute;
  top: var(--gv-space-2);
  right: var(--gv-space-2);
  z-index: 5;
  scroll-margin-top: calc(var(--gv-size-topbar) + var(--gv-space-4));
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container-highest);
  box-shadow: var(--gv-elev-2);
  cursor: pointer;
}

.library-card__check input {
  width: 20px;
  height: 20px;
  accent-color: var(--gv-color-primary);
  cursor: pointer;
}

.library__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}

@media (min-width: 840px) {
  .library {
    gap: var(--gv-space-5);
  }
}
</style>
