<script setup lang="ts">
/**
 * Local library (DESIGN.md C19).
 *
 * Page skeleton: PageHeader → one-line Toolbar (tag-aware search, search,
 * FilterButton with the active-condition count, sort, view switch) → active
 * filter chips → collapsible filter panel (Sheet below 600px) → SelectionBar
 * (only with a selection) → GalleryCollection.
 *
 * The whole filter state lives in one `LibraryFilters` object (`./filters.ts`)
 * that is the single source for the URL query, the request parameters and the
 * chip row. Tag clicks on a card / row / table cell are handled by the shared
 * collection components with `useTagNavigation("local")`, which appends to
 * `tags=` and pins `tag_mode=and` (idempotent).
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Chip from "@/components/ui/Chip.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import FilterButton from "@/components/ui/FilterButton.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Select from "@/components/ui/Select.vue";
import Sheet from "@/components/ui/Sheet.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import GalleryActions from "@/components/actions/GalleryActions.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import {
  LOCAL_TABLE_COLUMNS,
  orderByFor,
  type SortState,
  type TableColumn,
} from "@/components/gallery/table-columns";
import { tagKey, tagLabel, type TagLike } from "@/components/tags/tag-utils";
import { useViewMode } from "@/composables/useViewMode";
import { fetchLists, type GalleryList } from "@/api/lists";
import type { TagSuggestion } from "@/api/library";
import { useLibraryStore, type GalleryListQuery } from "@/stores/library";
import { useFavoritesStore } from "@/stores/favorites";
import { useSettingsStore } from "@/stores/settings";
import TagSuggest from "./TagSuggest.vue";
import LibraryFilterPanel from "./LibraryFilterPanel.vue";
import LibraryManageBar from "./manage/LibraryManageBar.vue";
import { useGallerySelection } from "./manage/useSelection";
import { ensureLibraryManageMessages } from "./manage/messages";
import { ensureLibraryMessages } from "./messages";
import {
  activeConditions,
  activeFilterCount,
  appendTagCondition,
  defaultFilters,
  filtersFromQuery,
  filtersToUrlQuery,
  firstQuery,
  hasAdvancedFilters,
  removeTagToken,
  tagTokenToTag,
  toGalleryQuery,
  type FilterCondition,
  type LibraryFilters,
} from "./filters";

ensureLibraryMessages();
ensureLibraryManageMessages();

const { t, locale } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useLibraryStore();
const settings = useSettingsStore();
const favorites = useFavoritesStore();
const selection = useGallerySelection();

const view = useViewMode("library", {
  allowed: ["grid", "list", "table"] as const,
  fallback: "grid",
});
const viewMode = computed(() => view.mode.value);
const viewModes = computed(() => view.available.value);
const compact = computed(() => view.isCompact.value);

const filters = ref<LibraryFilters>(defaultFilters(settings.pageSize));
const filtersOpen = ref(false);
const panelClosedByUser = ref(false);
const lists = ref<GalleryList[]>([]);
const tagDisplays = ref(new Map<string, TagLike>());

const galleryQuery = computed<GalleryListQuery>(() => withRouteTagMode(toGalleryQuery(filters.value)));

/** The URL's `tag_mode` / `tag_match` are part of the effective query. */
function withRouteTagMode(query: GalleryListQuery): GalleryListQuery {
  const mode = firstQuery(route.query.tag_mode);
  const match = firstQuery(route.query.tag_match);
  return {
    ...query,
    ...(mode === "and" || mode === "or" ? { tag_mode: mode } : {}),
    ...(match === "exact" || match === "fuzzy" ? { tag_match: match } : {}),
  };
}
const activeCount = computed(() => activeFilterCount(filters.value));
const totalLabel = computed(() => t("library.page.totalBooks", { n: store.total }));

/**
 * Library table columns: the shared set minus the low-value date / progress /
 * status cells, so the tag column (3 + N) still fits at 1280 with the drawer
 * open. Selection, cover, title, category, tags, pages, size, rating, actions
 * stay; the grid and list views keep showing dates and progress.
 */
const tableColumns = LOCAL_TABLE_COLUMNS.filter(
  (column) => !["posted", "progress", "status"].includes(column.key),
);

const selectedIds = computed(() => selection.list.value);
const selectedItems = computed(() => store.items.filter((item) => selection.has(item.id)));

const sort = computed<SortState | null>(() => {
  const match = /^(title|posted_at|page_count|file_size|rating|id)_(asc|desc)$/.exec(
    filters.value.orderBy,
  );
  if (!match) return null;
  const column = LOCAL_TABLE_COLUMNS.find((entry) => entry.sortKey === match[1]);
  if (!column) return null;
  return { key: column.key, direction: match[2] as "asc" | "desc" };
});

const orderOptions = computed(() => [
  { value: "id_desc", label: t("legacy.orderDefault") },
  { value: "posted_at_desc", label: t("legacy.orderPosted") },
  { value: "title_asc", label: t("legacy.orderTitle") },
  { value: "page_count_desc", label: t("legacy.orderPages") },
  { value: "file_size_desc", label: t("legacy.orderSize") },
  { value: "rating_desc", label: t("legacy.orderRating") },
]);

const CATEGORY_KEYS: Record<string, string> = {
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

function categoryLabel(value: string): string {
  return t(`legacy.${CATEGORY_KEYS[value] ?? "catMisc"}`);
}

function readStatusLabel(value: string): string {
  if (value === "unread") return t("legacy.readStatusUnread");
  if (value === "reading") return t("legacy.readStatusReading");
  if (value === "completed") return t("legacy.readStatusCompleted");
  return value;
}

function qualityLabel(value: string): string {
  if (value === "original") return t("legacy.qualityOriginal");
  if (value === "resample") return t("legacy.qualityResample");
  return value;
}

function listLabel(value: string): string {
  const found = lists.value.find((item) => String(item.id) === value);
  return found ? found.name : value;
}

const tagLookup = computed(() => {
  const map = new Map<string, TagLike>();
  for (const item of store.items) {
    for (const tag of item.tags ?? []) map.set(tagKey(tag), tag);
  }
  for (const [key, tag] of tagDisplays.value) map.set(key, tag);
  return map;
});

interface ConditionChip {
  key: string;
  label: string;
  /** Raw `namespace:name` for tag chips (used by e2e and the tooltip). */
  tag?: string;
  condition: FilterCondition;
}

function tagChipLabel(token: string): string {
  const excluded = token.startsWith("-");
  const tag = tagLookup.value.get(tagKey(tagTokenToTag(token)));
  const text = tag ? tagLabel(tag, locale.value) : tagTokenToTag(token).name;
  return excluded ? `- ${text}` : text;
}

function conditionLabel(condition: FilterCondition): string {
  const value = condition.value;
  switch (condition.kind) {
    case "q":
      return t("library.page.chipSearch", { value });
    case "tag":
      return tagChipLabel(value);
    case "category":
      return t("library.page.chipCategory", { value: categoryLabel(value) });
    case "read_status":
      return t("library.page.chipReadStatus", { value: readStatusLabel(value) });
    case "page_min":
      return t("library.page.chipPageMin", { value });
    case "page_max":
      return t("library.page.chipPageMax", { value });
    case "min_rating":
      return t("library.page.chipRating", { value });
    case "size_min":
      return t("library.page.chipSizeMin", { value });
    case "size_max":
      return t("library.page.chipSizeMax", { value });
    case "posted_from":
      return t("library.page.chipPostedFrom", { value });
    case "posted_to":
      return t("library.page.chipPostedTo", { value });
    case "uploader":
      return t("library.page.chipUploader", { value });
    case "image_quality":
      return t("library.page.chipQuality", { value: qualityLabel(value) });
    case "min_local_rating":
      return t("library.page.chipLocalRating", { value });
    case "list_id":
      return t("library.page.chipList", { value: listLabel(value) });
    default:
      return value;
  }
}

const chips = computed<ConditionChip[]>(() =>
  activeConditions(filters.value).map((condition) => ({
    key: `${condition.kind}:${condition.value}`,
    label: conditionLabel(condition),
    tag: condition.kind === "tag" ? condition.value : undefined,
    condition,
  })),
);

function isFavorited(item: {
  gid: number | null;
  favorite?: boolean;
  favorite_category?: number | null;
}): boolean {
  if (!item.gid) return Boolean(item.favorite);
  return favorites.ensure(item.gid, {
    favorited: Boolean(item.favorite),
    favcat: item.favorite_category ?? null,
  }).favorited;
}

function onSelectionChange(id: number, next: boolean): void {
  selection.toggle(id, next);
}

/** Re-read the page from the server so deleted rows and totals stay honest. */
function onRemoved(): void {
  selection.clear();
  void store.reload();
}

/** Reflect cloud-confirmed favourites on the visible cards. */
function onFavorited(gids: number[]): void {
  const added = new Set(gids);
  for (const item of store.items) {
    if (item.gid && added.has(item.gid)) item.favorite = true;
  }
}

function pushFilters(next: LibraryFilters, extra: Record<string, string> = {}): void {
  filters.value = next;
  const query = filtersToUrlQuery(next, {
    tag_mode: firstQuery(route.query.tag_mode),
    tag_match: firstQuery(route.query.tag_match),
    ...extra,
  });
  void router.push({ name: "library", query });
}

/** Panel patches stay local; the URL is pushed on `commit` (change / select). */
function onFiltersChange(next: LibraryFilters): void {
  filters.value = next;
}

function onFiltersCommit(): void {
  const next = filters.value;
  if (next.pageSize !== settings.pageSize) settings.setPageSize(next.pageSize);
  pushFilters(next);
}

function onSearch(): void {
  pushFilters({ ...filters.value, term: filters.value.term });
}

function onSelectTag(tag: TagSuggestion): void {
  const condensed = appendTagCondition(filters.value.tags, tag);
  const key = tagKey(tag);
  tagDisplays.value = new Map(tagDisplays.value).set(key, tag);
  pushFilters(
    { ...filters.value, term: "", tags: condensed.tags },
    { tag_mode: condensed.tag_mode },
  );
}

function onOrderChange(value: string): void {
  pushFilters({ ...filters.value, orderBy: value });
}

function onSort(column: TableColumn, direction: "asc" | "desc"): void {
  const orderBy = orderByFor(column, direction);
  if (!orderBy) return;
  pushFilters({ ...filters.value, orderBy });
}

function removeCondition(condition: FilterCondition): void {
  const next: LibraryFilters = { ...filters.value };
  switch (condition.kind) {
    case "q":
      next.term = "";
      break;
    case "tag":
      next.tags = removeTagToken(next.tags, condition.value);
      break;
    case "category":
      next.category = "";
      break;
    case "read_status":
      next.readStatus = "";
      break;
    case "page_min":
      next.pageMin = "";
      break;
    case "page_max":
      next.pageMax = "";
      break;
    case "min_rating":
      next.minRating = "";
      break;
    case "size_min":
      next.sizeMin = "";
      break;
    case "size_max":
      next.sizeMax = "";
      break;
    case "posted_from":
      next.postedFrom = "";
      break;
    case "posted_to":
      next.postedTo = "";
      break;
    case "uploader":
      next.uploader = "";
      break;
    case "image_quality":
      next.imageQuality = "";
      break;
    case "min_local_rating":
      next.minLocalRating = "";
      break;
    case "list_id":
      next.listId = "";
      break;
    default:
      break;
  }
  pushFilters(next);
}

function clearAll(): void {
  pushFilters({ ...defaultFilters(settings.pageSize), orderBy: "id_desc" });
}

function toggleFilters(): void {
  filtersOpen.value = !filtersOpen.value;
  panelClosedByUser.value = !filtersOpen.value;
}

function closeFilters(): void {
  filtersOpen.value = false;
  panelClosedByUser.value = true;
}

function syncFromRoute(): void {
  filters.value = filtersFromQuery(route.query, settings.pageSize);
  if (hasAdvancedFilters(filters.value) && !panelClosedByUser.value) {
    filtersOpen.value = true;
  }
  store.start(galleryQuery.value, settings.pageSize);
  restoreScrollSoon();
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

async function loadLists(): Promise<void> {
  try {
    lists.value = await fetchLists();
  } catch {
    lists.value = [];
  }
}

onMounted(() => {
  syncFromRoute();
  void loadLists();
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
    <PageHeader
      :title="t('library.page.title')"
      :count="store.total ? totalLabel : ''"
      :count-label="totalLabel"
      testid="library-header"
    />

    <form class="library__search-form" role="search" @submit.prevent="onSearch">
      <Toolbar testid="library-toolbar">
        <TagSuggest
          class="library__search"
          :model-value="filters.term"
          :label="t('library.page.search')"
          :placeholder="t('library.page.searchPlaceholder')"
          @update:model-value="onFiltersChange({ ...filters, term: $event })"
          @select="onSelectTag"
        />
        <ToolbarGroup end>
          <Button type="submit" icon="search" data-testid="library-search-submit">
            {{ t("legacy.search") }}
          </Button>
          <FilterButton
            :count="activeCount"
            :label="t('library.page.filters')"
            :aria-expanded="filtersOpen"
            aria-controls="library-advanced-filters"
            testid="advanced-toggle"
            @click="toggleFilters"
          />
          <Select
            class="library__sort"
            data-testid="order-select"
            :model-value="filters.orderBy"
            :options="orderOptions"
            :aria-label="t('library.page.orderLabel')"
            @update:model-value="onOrderChange"
          />
          <ViewModeToggle
            :model-value="viewMode"
            :options="viewModes"
            @update:model-value="view.setMode"
          />
        </ToolbarGroup>
      </Toolbar>
    </form>

    <div
      v-if="chips.length"
      class="library__chips"
      data-testid="active-filters"
      :aria-label="t('library.page.activeFiltersLabel')"
    >
      <Chip
        v-for="chip in chips"
        :key="chip.key"
        icon="close"
        :label="chip.label"
        :title="chip.tag ? `${chip.tag} — ${t('library.page.removeFilter')}` : t('library.page.removeFilter')"
        :data-tag="chip.tag"
        data-testid="active-filter-chip"
        @click="removeCondition(chip.condition)"
      />
    </div>

    <Sheet
      v-if="compact"
      :open="filtersOpen"
      :title="t('library.page.filtersTitle')"
      testid="library-filter-sheet"
      @close="closeFilters"
    >
      <LibraryFilterPanel
        :model-value="filters"
        :lists="lists"
        :query="galleryQuery"
        @update:model-value="onFiltersChange"
        @commit="onFiltersCommit"
        @clear="clearAll"
        @lists-changed="loadLists"
        @removed="onRemoved"
      />
      <template #footer>
        <Button variant="text" @click="closeFilters">{{ t("common.close") }}</Button>
      </template>
    </Sheet>

    <LibraryFilterPanel
      v-else-if="filtersOpen"
      :model-value="filters"
      :lists="lists"
      :query="galleryQuery"
      @update:model-value="onFiltersChange"
      @commit="onFiltersCommit"
      @clear="clearAll"
      @lists-changed="loadLists"
      @removed="onRemoved"
    />

    <LibraryManageBar
      :selected="selectedItems"
      :lists="lists"
      :default-list-id="filters.listId"
      @clear="selection.clear()"
      @removed="onRemoved"
      @favorited="onFavorited"
    />

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

    <template v-else-if="!store.items.length">
      <!-- C18: an empty table keeps its header (only the table view). -->
      <GalleryCollection
        v-if="viewMode === 'table'"
        :items="[]"
        mode="table"
        :columns="tableColumns"
        :sort="sort"
        testid="library-grid"
        @sort="onSort"
      />
      <EmptyState
        :title="t('library.page.emptyTitle')"
        :body="t('library.page.emptyBody')"
        :action-label="activeCount ? t('library.page.clearFilters') : ''"
        testid="library-empty"
        @action="clearAll"
      />
    </template>

    <GalleryCollection
      v-else
      :items="store.items"
      :mode="viewMode"
      :columns="tableColumns"
      :sort="sort"
      selectable
      :selected="selectedIds"
      :loading="store.loading"
      :has-more="store.hasMore"
      :error="store.error"
      :failures="store.failures"
      :total="store.total"
      testid="library-grid"
      @load-more="store.loadMore"
      @retry="store.retry"
      @sort="onSort"
      @select="onSelectionChange"
    >
      <template #card="{ item }">
        <div
          class="library-card"
          :class="{ 'library-card--selected': selection.has(item.id) }"
          data-testid="library-card"
          :data-id="item.id"
        >
          <GalleryCard
            :item="item"
            :variant="viewMode === 'list' ? 'list' : 'grid'"
            selectable
            :selected="selection.has(item.id)"
            tag-source="local"
            :favorited="isFavorited(item)"
            @select="onSelectionChange"
          >
            <template #actions>
              <GalleryActions
                v-if="item.gid"
                density="card"
                :gid="item.gid"
                :token="item.token ?? ''"
                :title="item.title"
                :favorited="isFavorited(item)"
                :favcat="item.favorite_category ?? null"
                :in-library="true"
                :show-read="false"
              />
            </template>
          </GalleryCard>
        </div>
      </template>
      <template #actions="{ item }">
        <GalleryActions
          v-if="item.gid"
          density="card"
          :gid="item.gid"
          :token="item.token ?? ''"
          :title="item.title"
          :favorited="isFavorited(item)"
          :favcat="item.favorite_category ?? null"
          :in-library="true"
          :show-read="false"
        />
      </template>
    </GalleryCollection>
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

.library__search-form {
  width: 100%;
}

.library__search {
  flex: 1 1 220px;
  min-width: 0;
}

.library__sort {
  flex: none;
  width: 190px;
}

.library__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.library-card {
  position: relative;
  min-width: 0;
}

.library-card--selected {
  outline: 2px solid var(--gv-color-primary);
  outline-offset: 2px;
  border-radius: var(--gv-radius-md);
}

.library__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}

@media (max-width: 599.98px) {
  .library {
    gap: var(--gv-space-3);
  }

  .library__sort {
    flex: 1 1 140px;
    width: auto;
  }

  /* Let the action group wrap on its own line instead of overflowing; the
     Toolbar itself only wraps whole items (audit LB-01 / toolbar at 390). */
  .library__search-form :deep([data-gv-toolbar-group]) {
    flex: 1 1 100%;
    width: 100%;
    flex-wrap: wrap;
    margin-inline-start: 0;
  }

  /* The view switch gets its own trailing line instead of a lonely first cell. */
  .library__search-form :deep(.view-mode-toggle) {
    margin-inline-start: auto;
  }
}

@media (min-width: 840px) {
  .library {
    gap: var(--gv-space-5);
  }
}
</style>
