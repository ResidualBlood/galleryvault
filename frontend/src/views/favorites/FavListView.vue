<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Chip from "@/components/ui/Chip.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import FilterButton from "@/components/ui/FilterButton.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import ArchiveDialog from "@/components/system/ArchiveDialog.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import { PAGE_SIZES, clampPageSize } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
import { useViewMode } from "@/composables/useViewMode";
import {
  checkFavoriteCategory,
  downloadSelectedFavorites,
  fetchFavoriteCategories,
  fetchFavoriteItems,
  moveFavorite,
  removeFavorite,
  type FavoriteCategory,
  type FavoriteItem,
} from "@/api/favorites";
import type { GalleryItem } from "@/api/library";
import type { TableColumn } from "@/components/gallery/table-columns";
import {
  activeFavFilterCount,
  buildFavListParams,
  emptyFavListFilters,
  favListQuery,
  filtersFromQuery,
  type FavListFilters,
} from "./filters";
import {
  FAV_TABLE_COLUMNS,
  favTableSort,
  favoriteBadges,
  favoriteFolderTitle,
  favoriteToGalleryItem,
} from "./items";
import { ensureFavoritesMessages } from "./messages";

ensureFavoritesMessages();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const view = useViewMode("favlist");

const favcat = computed(() => {
  const parsed = Number.parseInt(String(route.params.id ?? ""), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
});

const filters = ref<FavListFilters>(emptyFavListFilters(settings.pageSize));
const advancedOpen = ref(false);
const favoriteItems = ref<FavoriteItem[]>([]);
const total = ref(0);
const loadedPage = ref(0);
const loading = ref(true);
const loadingMore = ref(false);
const error = ref("");
const categories = ref<FavoriteCategory[]>([]);
const selected = ref<number[]>([]);
const sentinel = ref<HTMLElement | null>(null);
const dialog = ref<"" | "move" | "remove" | "archive">("");
const moveTarget = ref("");
const busy = ref(false);
const checking = ref(false);
let requestSeq = 0;
let observer: IntersectionObserver | null = null;

const folderTitle = computed(() => {
  const folder = categories.value.find((item) => item.favcat === favcat.value);
  return favoriteFolderTitle(folder?.name, favcat.value, t);
});

const galleryItems = computed<GalleryItem[]>(() =>
  favoriteItems.value.map(favoriteToGalleryItem),
);

const categoryOptions = computed(() => [
  { value: "", label: t("legacy.allCategories") },
  ...[
    "doujinshi",
    "manga",
    "artistcg",
    "gamecg",
    "western",
    "non-h",
    "image_set",
    "cosplay",
    "asianporn",
    "misc",
    "deleted",
  ].map((value) => ({ value, label: categoryLabel(value) })),
]);

const orderOptions = computed(() => [
  { value: "last_seen_desc", label: t("legacy.orderDefault") },
  { value: "first_seen_desc", label: t("legacy.orderFirstSeen") },
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

const ratingOptions = computed(() => [
  { value: "", label: t("legacy.minRating") },
  { value: "2", label: "≥ 2" },
  { value: "3", label: "≥ 3" },
  { value: "4", label: "≥ 4" },
  { value: "4.5", label: "≥ 4.5" },
]);

const qualityOptions = computed(() => [
  { value: "", label: t("legacy.qualityAll") },
  { value: "original", label: t("legacy.qualityOriginal") },
  { value: "resample", label: t("legacy.qualityResample") },
]);

const languageOptions = computed(() => [
  { value: "", label: t("legacy.languageAll") },
  { value: "chinese", label: t("legacy.langChinese") },
  { value: "english", label: t("legacy.langEnglish") },
  { value: "japanese", label: t("legacy.langJapanese") },
  { value: "korean", label: t("legacy.langKorean") },
  { value: "translated", label: t("legacy.langTranslated") },
]);

const localRatingOptions = computed(() => [
  { value: "", label: t("legacy.localRatingMin") },
  ...[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: `≥ ${value}` })),
]);

const stateOptions = computed(() => [
  { value: "all", label: t("favorites.list.stateAll") },
  { value: "local", label: t("favorites.list.stateLocal") },
  { value: "cloud", label: t("favorites.list.stateCloud") },
]);

const pagerSizes = computed(() => {
  const values = new Set(PAGE_SIZES.map(String));
  values.add(String(settings.pageSize));
  values.add(String(filters.value.page_size));
  return [...values].map(Number).sort((a, b) => a - b);
});

const moveOptions = computed(() =>
  categories.value
    .filter((item) => item.favcat !== favcat.value)
    .map((item) => ({
      value: String(item.favcat),
      label: favoriteFolderTitle(item.name, item.favcat, t),
    })),
);

const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / Math.max(1, filters.value.page_size))),
);

const activeTagList = computed(() =>
  filters.value.tags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean),
);

const advancedCount = computed(() => activeFavFilterCount(filters.value));
const allLoaded = computed(() => favoriteItems.value.length >= total.value);
const hasSelection = computed(() => selected.value.length > 0);
const allSelected = computed(
  () =>
    galleryItems.value.length > 0 &&
    galleryItems.value.every((item) => selected.value.includes(item.id)),
);
const tableColumns = computed<readonly TableColumn[]>(() => FAV_TABLE_COLUMNS);
const tableSort = computed(() => favTableSort(filters.value.order_by));

const queryFrom = computed(() => {
  const value = route.query.from;
  return (Array.isArray(value) ? value[0] : value) ?? "";
});

const crumbs = computed(() => {
  const items: Array<{ label: string; to?: string }> = [
    { label: t("legacy.favorites"), to: "/favorites" },
  ];
  if (queryFrom.value) {
    items.push({ label: t("legacy.backToGallery"), to: `/gallery/${queryFrom.value}` });
  }
  items.push({ label: folderTitle.value });
  return items;
});

function first(value: unknown): string {
  if (Array.isArray(value)) return first(value[0]);
  return value === null || value === undefined ? "" : String(value);
}

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

function externalUrl(item: FavoriteItem): string {
  if (item.url && /^https?:\/\//i.test(item.url)) return item.url;
  return `https://e-hentai.org/g/${item.gid}/${encodeURIComponent(item.token)}/`;
}

function withFrom(query: Record<string, string>): Record<string, string> {
  const from = first(route.query.from);
  return from ? { ...query, from } : query;
}

function queryForPage(page: number): Record<string, string> {
  return withFrom(favListQuery({ ...filters.value, page }));
}

function syncFromRoute(): void {
  const next = filtersFromQuery(
    route.query as Record<string, unknown>,
    settings.pageSize,
  );
  next.page_size = clampPageSize(next.page_size, settings.pageSize);
  filters.value = next;
  if (activeFavFilterCount(next) > 0) advancedOpen.value = true;
  void loadInitial();
}

async function loadInitial(): Promise<void> {
  const seq = ++requestSeq;
  loading.value = true;
  error.value = "";
  selected.value = [];
  try {
    const page = filters.value.page;
    const data = await fetchFavoriteItems(favcat.value, buildFavListParams(filters.value));
    if (seq !== requestSeq) return;
    favoriteItems.value = data.items;
    total.value = data.total;
    loadedPage.value = page;
  } catch (cause) {
    if (seq !== requestSeq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
    favoriteItems.value = [];
    total.value = 0;
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

async function loadMore(): Promise<void> {
  if (loading.value || loadingMore.value || allLoaded.value) return;
  const seq = requestSeq;
  loadingMore.value = true;
  try {
    const nextPage = loadedPage.value + 1;
    const data = await fetchFavoriteItems(
      favcat.value,
      buildFavListParams({ ...filters.value, page: nextPage }),
    );
    if (seq !== requestSeq) return;
    const known = new Set(favoriteItems.value.map((item) => item.gid));
    favoriteItems.value = [
      ...favoriteItems.value,
      ...data.items.filter((item) => !known.has(item.gid)),
    ];
    total.value = data.total;
    loadedPage.value = nextPage;
  } catch (cause) {
    if (seq === requestSeq) {
      ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
    }
  } finally {
    if (seq === requestSeq) loadingMore.value = false;
  }
}

function applyFilters(): void {
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  if (query.tags === "") delete query.tags;
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function setState(state: string): void {
  filters.value.state = state as FavListFilters["state"];
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function clearFilters(): void {
  filters.value = emptyFavListFilters(settings.pageSize);
  advancedOpen.value = false;
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function onPageSize(value: number): void {
  const next = clampPageSize(String(value), settings.pageSize);
  settings.setPageSize(next);
  filters.value.page_size = next;
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function goPage(page: number): void {
  if (page === filters.value.page) return;
  void router.push({
    name: "favorites-list",
    params: { id: favcat.value },
    query: queryForPage(page),
  });
}

function removeTag(tag: string): void {
  filters.value.tags = activeTagList.value.filter((item) => item !== tag).join(",");
  applyFilters();
}

function toggleSelected(id: number, next: boolean): void {
  const has = selected.value.includes(id);
  if (next && !has) selected.value = [...selected.value, id];
  if (!next && has) selected.value = selected.value.filter((value) => value !== id);
}

function selectAllLoaded(): void {
  selected.value = galleryItems.value.map((item) => item.id);
}

function clearSelection(): void {
  selected.value = [];
}

function badgesFor(item: GalleryItem) {
  return favoriteBadges(item, t);
}

/**
 * Favourites mix local and cloud-only entries: cloud rows have no local
 * gallery to open, so the card link is redirected to ExHentai instead of the
 * detail route. The capture handler runs before the card's own RouterLink, so
 * the browser never follows the local `#/gallery/<id>` fallback.
 */
function onCollectionClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null;
  const link = target?.closest<HTMLElement>(
    ".gallery-card__link, .gallery-list-row__link, .gallery-table-row__link",
  );
  if (!link) return;
  const host = link.closest<HTMLElement>("[data-id]");
  const id = Number.parseInt(host?.dataset.id ?? "", 10);
  const source = favoriteItems.value.find((item) => item.gid === id);
  if (!source) return;
  event.preventDefault();
  event.stopPropagation();
  openFavorite(source);
}

function openFavorite(item: FavoriteItem): void {
  if (item.gallery_id) {
    void router.push({
      name: "gallery",
      params: { id: item.gallery_id },
      query: withFrom({}),
    });
    return;
  }
  window.open(externalUrl(item), "_blank", "noopener");
}

function onSort(column: TableColumn, direction: "asc" | "desc"): void {
  if (column.sortKey !== "title") return;
  filters.value.order_by = direction === "asc" ? "title_asc" : "title_desc";
  applyFilters();
}

/** Legacy favorites.js `checkFavoriteCategory(favcat)`: start one folder scan. */
async function checkFolder(): Promise<void> {
  if (checking.value) return;
  checking.value = true;
  try {
    await checkFavoriteCategory(favcat.value);
    ui.success(
      `${t("favorites.list.checkFolderStarted")} #${favcat.value}${folderTitle.value ? ` · ${folderTitle.value}` : ""}`,
    );
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
  } finally {
    checking.value = false;
  }
}

async function queueSelected(
  quality?: "original" | "resample",
  archive = false,
): Promise<boolean> {
  if (!hasSelection.value || busy.value) return false;
  busy.value = true;
  try {
    const result = await downloadSelectedFavorites(selected.value, { quality, archive });
    const parts = [`${t("legacy.favDlQueued")}: ${result.queued}`];
    if (result.skipped) parts.push(`${t("legacy.favDlSkip")}: ${result.skipped}`);
    ui.success(parts.join(" · "));
    clearSelection();
    return true;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
    return false;
  } finally {
    busy.value = false;
  }
}

async function confirmMove(): Promise<void> {
  if (busy.value || !hasSelection.value) return;
  const target = Number.parseInt(moveTarget.value, 10);
  if (!Number.isFinite(target) || target === favcat.value) return;
  busy.value = true;
  try {
    const result = await moveFavorite(selected.value, target);
    if (result.cloud_ok) {
      ui.success(t("legacy.favMoved"));
    } else {
      ui.info(
        t("legacy.favMovedPartial", {
          count: result.successful_gids.length || result.local_moved || 0,
          failed: result.cloud_failed.length,
        }),
      );
    }
    dialog.value = "";
    clearSelection();
    await loadInitial();
    const refreshed = await fetchFavoriteCategories();
    categories.value = refreshed;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
  } finally {
    busy.value = false;
  }
}

async function confirmRemove(): Promise<void> {
  if (busy.value || !hasSelection.value) return;
  busy.value = true;
  try {
    const result = await removeFavorite(selected.value);
    if (result.cloud_ok) {
      ui.success(t("legacy.unfavorited"));
    } else {
      ui.info(t("legacy.unfavoritedLocal"));
    }
    dialog.value = "";
    clearSelection();
    await loadInitial();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
  } finally {
    busy.value = false;
  }
}

function openMove(): void {
  if (!hasSelection.value) return;
  moveTarget.value = moveOptions.value[0]?.value ?? "";
  dialog.value = "move";
}

function openRemove(): void {
  if (!hasSelection.value) return;
  dialog.value = "remove";
}

function openArchive(): void {
  if (!hasSelection.value) return;
  dialog.value = "archive";
}

/** Close the preview first so clearing the selection cannot re-trigger it. */
async function confirmArchive(payload: {
  gids: number[];
  quality: "original" | "resample";
}): Promise<void> {
  dialog.value = "";
  await queueSelected(payload.quality, true);
}

function bindObserver(): void {
  if (typeof IntersectionObserver === "undefined") return;
  observer?.disconnect();
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadMore();
    },
    { rootMargin: "900px 0px" },
  );
  if (sentinel.value) observer.observe(sentinel.value);
}

watch(sentinel, () => bindObserver());
watch(
  () => route.query,
  () => syncFromRoute(),
  { immediate: true, deep: true },
);

onMounted(async () => {
  try {
    categories.value = await fetchFavoriteCategories();
  } catch {
    /* Folder names are cosmetic; the list still works. */
  }
  bindObserver();
});

onBeforeUnmount(() => {
  requestSeq += 1;
  observer?.disconnect();
});
</script>

<template>
  <section class="favlist" data-testid="favlist-view">
    <PageHeader
      :title="folderTitle"
      :count="total"
      :count-label="t('favorites.list.total', { n: total })"
      :subtitle="t('legacy.favListSub')"
      :crumbs="crumbs"
      testid="favlist-header"
    />

    <form class="favlist__search" role="search" @submit.prevent="applyFilters">
      <Toolbar testid="favlist-toolbar">
        <ToolbarGroup class="favlist__search-group">
          <Input
            v-model="filters.q"
            class="favlist__search-input"
            icon="search"
            clearable
            :clear-label="t('favorites.list.clearFilters')"
            :placeholder="t('legacy.favSearchPlaceholder')"
            :aria-label="t('legacy.search')"
            data-testid="favlist-q"
          />
          <IconButton
            name="search"
            type="submit"
            :label="t('legacy.search')"
            data-testid="favlist-search-submit"
          />
        </ToolbarGroup>

        <ToolbarGroup>
          <SegmentedControl
            :model-value="filters.state"
            :options="stateOptions"
            :label="t('favorites.list.stateLabel')"
            testid="favlist-state"
            @change="setState"
          />
        </ToolbarGroup>

        <ToolbarGroup end>
          <ToolbarGroup collapsible :label="t('legacy.library_filters_advanced')">
            <Select
              v-model="filters.order_by"
              class="favlist__order"
              :options="orderOptions"
              :aria-label="t('favorites.list.sort')"
              data-testid="favlist-order"
              @change="applyFilters"
            />
            <FilterButton
              :count="advancedCount"
              :icon="advancedOpen ? 'chevron-up' : 'filter'"
              :aria-expanded="advancedOpen"
              data-testid="favlist-advanced-toggle"
              @click="advancedOpen = !advancedOpen"
            />
            <Button
              variant="outlined"
              :loading="checking"
              data-testid="favlist-check"
              @click="checkFolder"
            >
              {{ t("favorites.list.checkFolder") }}
            </Button>
          </ToolbarGroup>
          <ViewModeToggle
            :model-value="view.mode.value"
            :options="view.available.value"
            @update:model-value="view.setMode"
          />
        </ToolbarGroup>
      </Toolbar>
    </form>

    <div v-if="advancedOpen" class="favlist__advanced" data-testid="favlist-advanced">
      <div class="favlist__grid-fields">
        <Select
          v-model="filters.category"
          :options="categoryOptions"
          :label="t('favorites.list.category')"
          data-testid="favlist-category"
        />
        <Select
          v-model="filters.language"
          :options="languageOptions"
          :label="t('favorites.list.language')"
          data-testid="favlist-language"
        />
        <Select
          v-model="filters.read_status"
          :options="readStatusOptions"
          :label="t('legacy.readStatusAll')"
          data-testid="favlist-read-status"
        />
        <Select
          v-model="filters.min_rating"
          :options="ratingOptions"
          :label="t('legacy.minRating')"
          data-testid="favlist-min-rating"
        />
        <Select
          v-model="filters.image_quality"
          :options="qualityOptions"
          :label="t('legacy.qualityAll')"
          data-testid="favlist-image-quality"
        />
        <Select
          v-model="filters.min_local_rating"
          :options="localRatingOptions"
          :label="t('legacy.localRatingMin')"
          data-testid="favlist-local-rating"
        />
        <Input
          v-model="filters.page_min"
          type="number"
          :label="t('legacy.pageMin')"
          data-testid="favlist-page-min"
        />
        <Input
          v-model="filters.page_max"
          type="number"
          :label="t('legacy.pageMax')"
          data-testid="favlist-page-max"
        />
        <Input
          v-model="filters.size_min"
          type="number"
          :label="t('legacy.sizeMin')"
          data-testid="favlist-size-min"
        />
        <Input
          v-model="filters.size_max"
          type="number"
          :label="t('legacy.sizeMax')"
          data-testid="favlist-size-max"
        />
        <Input
          v-model="filters.posted_from"
          type="date"
          :label="t('legacy.postedFrom')"
          data-testid="favlist-posted-from"
        />
        <Input
          v-model="filters.posted_to"
          type="date"
          :label="t('legacy.postedTo')"
          data-testid="favlist-posted-to"
        />
        <Input
          v-model="filters.uploader"
          :label="t('legacy.uploader')"
          data-testid="favlist-uploader"
        />
      </div>
      <div class="favlist__advanced-actions">
        <Button variant="text" type="button" data-testid="favlist-clear" @click="clearFilters">
          {{ t("favorites.list.clearFilters") }}
        </Button>
        <Button variant="tonal" type="button" icon="filter" @click="applyFilters">
          {{ t("favorites.list.applyFilters") }}
        </Button>
      </div>
    </div>

    <div v-if="activeTagList.length" class="favlist__chips">
      <Chip
        v-for="tag in activeTagList"
        :key="tag"
        :label="tag"
        selected
        :title="`${t('favorites.list.clearFilters')}: ${tag}`"
        testid="favlist-active-tag"
        @click="removeTag(tag)"
      />
    </div>

    <SelectionBar
      :count="selected.length"
      :label="t('favorites.list.selectedCount', { n: selected.length })"
      testid="favlist-selection"
      @clear="clearSelection"
    >
      <Button
        v-if="!allSelected"
        variant="text"
        icon="all-selected"
        type="button"
        data-testid="favlist-select-all"
        @click="selectAllLoaded"
      >
        {{ t("favorites.list.selectAll") }}
      </Button>
      <Button :loading="busy" type="button" data-testid="favlist-download" @click="queueSelected()">
        {{ t("legacy.favDl") }} ({{ selected.length }})
      </Button>
      <Button
        variant="outlined"
        type="button"
        data-testid="favlist-download-original"
        @click="queueSelected('original')"
      >
        {{ t("legacy.favDlOrig") }} ({{ selected.length }})
      </Button>
      <Button variant="outlined" type="button" data-testid="favlist-archive" @click="openArchive">
        {{ t("legacy.favDlArchive") }} ({{ selected.length }})
      </Button>
      <Button variant="outlined" type="button" data-testid="favlist-move" @click="openMove">
        {{ t("legacy.favMove") }} ({{ selected.length }})
      </Button>
      <template #danger>
        <Button
          variant="text"
          danger
          type="button"
          data-testid="favlist-remove"
          @click="openRemove"
        >
          {{ t("legacy.favRemove") }} ({{ selected.length }})
        </Button>
      </template>
    </SelectionBar>

    <ErrorState
      v-if="error && !favoriteItems.length"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('common.retry')"
      @retry="loadInitial"
    />

    <div v-else-if="loading" class="favlist__skeletons" aria-hidden="true">
      <Skeleton
        v-for="index in 12"
        :key="index"
        :variant="view.mode.value === 'list' ? 'list' : 'card'"
      />
    </div>

    <div v-else class="favlist__collection" @click.capture="onCollectionClick">
      <GalleryCollection
        v-if="favoriteItems.length || view.mode.value === 'table'"
        :items="galleryItems"
        :mode="view.mode.value"
        :columns="tableColumns"
        :sort="tableSort"
        :selectable="true"
        :selected="selected"
        :loading="loadingMore"
        :has-more="!allLoaded"
        :total="total"
        testid="favlist-grid"
        @load-more="loadMore"
        @select="toggleSelected"
        @sort="onSort"
      >
        <template #card="{ item }">
          <GalleryCard
            :item="item"
            :variant="view.mode.value === 'list' ? 'list' : 'grid'"
            :badges="badgesFor(item)"
            tag-source="favorites"
            selectable
            :selected="selected.includes(item.id)"
            @select="toggleSelected"
          />
        </template>
      </GalleryCollection>

      <EmptyState
        v-if="!favoriteItems.length"
        :title="t('legacy.noGalleries')"
        :body="t('favorites.list.empty')"
        testid="favlist-empty"
      />
    </div>

    <div ref="sentinel" class="favlist__sentinel" aria-hidden="true" />

    <Pager
      :page="filters.page"
      :total-pages="pageCount"
      :page-size="filters.page_size"
      :page-size-options="pagerSizes"
      testid="favlist-pager"
      @update:page="goPage"
      @update:page-size="onPageSize"
    />

    <Dialog
      :open="dialog === 'move'"
      :title="t('legacy.favMoveTitle')"
      testid="favlist-move-dialog"
      @close="dialog = ''"
    >
      <Select
        v-model="moveTarget"
        :options="moveOptions"
        :label="t('legacy.favMoveTarget')"
        data-testid="favlist-move-target"
      />
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button :loading="busy" data-testid="favlist-move-confirm" @click="confirmMove">
          {{ t("legacy.favMove") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="dialog === 'remove'"
      :title="t('legacy.favRemove')"
      testid="favlist-remove-dialog"
      @close="dialog = ''"
    >
      <p>{{ t("legacy.confirmFavRemove") }} ({{ selected.length }})</p>
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button danger :loading="busy" data-testid="favlist-remove-confirm" @click="confirmRemove">
          {{ t("legacy.favRemove") }}
        </Button>
      </template>
    </Dialog>

    <ArchiveDialog
      :open="dialog === 'archive'"
      :gids="selected"
      @close="dialog = ''"
      @confirm="confirmArchive"
    />
  </section>
</template>

<style scoped>
.favlist {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.favlist__search {
  display: block;
  width: 100%;
}

/* C12: a toolbar row keeps every control on one ladder step; only the search
   field grows, the SegmentedControl keeps its documented chip height. */
.favlist__search-group {
  flex: 1 1 140px;
  min-width: 96px;
}

.favlist__search-input {
  flex: 1 1 auto;
  min-width: 0;
}

.favlist__order {
  width: 180px;
}

.favlist__advanced {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.favlist__grid-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--gv-space-3);
}

.favlist__advanced-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--gv-space-2);
}

.favlist__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.favlist__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}

.favlist__collection {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  min-width: 0;
}

.favlist__sentinel {
  height: var(--gv-space-1);
}

@media (max-width: 599px) {
  .favlist__skeletons {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }

  .favlist__grid-fields {
    grid-template-columns: 1fr;
  }

  .favlist__search-group {
    flex: 1 1 100%;
  }
}
</style>
