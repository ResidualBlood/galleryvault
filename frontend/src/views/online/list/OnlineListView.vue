<script setup lang="ts">
/**
 * Online browse page (DESIGN C19, audit OL-01 … OL-13).
 *
 * PageHeader → one Toolbar row (search, filled search, filter, view toggle) →
 * a single-height filter row (list type + rating + category chips) → the
 * collection in grid / list / table, remembered per page. The list is the
 * default view. Tag clicks append an ExHentai exact query (`ns:"name$"`) to the
 * search box instead of issuing a second EH request.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Chip from "@/components/ui/Chip.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import FilterButton from "@/components/ui/FilterButton.vue";
import Input from "@/components/ui/Input.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import type { GalleryItem } from "@/api/library";
import type { OnlineListType } from "@/api/eh";
import type { TagLike } from "@/components/tags/tag-utils";
import { createDownloadsBatch } from "@/api/downloads";
import { addFavoritesBatch, type FavoriteCategory } from "@/api/favorites";
import { useFavoritesStore } from "@/stores/favorites";
import { readDefaultQuality, useDownloadsStore } from "@/stores/downloads";
import { useUiStore } from "@/stores/ui";
import { useViewMode } from "@/composables/useViewMode";
import {
  DEFAULT_ONLINE_FILTERS,
  ONLINE_CATEGORIES,
  enabledCategories,
  filtersToQuery,
  hasFilterQuery,
  loadOnlineDefaults,
  normalizeFilters,
  parseFiltersFromQuery,
  saveOnlineDefaults,
  toggleCategory,
  useOnlineStore,
  type OnlineCategory,
  type OnlineFilters,
} from "@/stores/online";
import OnlineListRow from "./OnlineListRow.vue";
import OnlineStateNotice from "./OnlineStateNotice.vue";
import { categoryToken } from "./category";
import { ensureOnlineMessages } from "./messages";
import {
  ONLINE_TABLE_COLUMNS,
  appendEhTagQuery,
  normalizePosted,
  withoutLanguageTags,
} from "./helpers";

ensureOnlineMessages();

const route = useRoute();
const router = useRouter();
const store = useOnlineStore();
const favorites = useFavoritesStore();
const downloads = useDownloadsStore();
const ui = useUiStore();
const { t } = useI18n();

const view = useViewMode("online", {
  allowed: ["grid", "list", "table"] as const,
  fallback: "list",
});

const filters = reactive<OnlineFilters>({ ...DEFAULT_ONLINE_FILTERS });
const term = ref("");
const filtersOpen = ref(true);
const skeletonCount = 6;

/* --------------------------------------------------------------- tag width */

const tagMax = ref(4);
let media: MediaQueryList | null = null;

function syncCompact(event?: MediaQueryListEvent): void {
  const compact = event ? event.matches : Boolean(media?.matches);
  tagMax.value = compact ? 3 : 4;
}

/* ---------------------------------------------------------- batch selection */

const selected = ref<number[]>([]);
const batchBusy = ref(false);
const batchFavoriteOpen = ref(false);
const favoriteTarget = ref("0");
const favoriteCategories = ref<FavoriteCategory[]>([]);
const selectedCount = computed(() => selected.value.length);

const favoriteOptions = computed(() => {
  const source = favoriteCategories.value.length
    ? favoriteCategories.value
    : Array.from({ length: 10 }, (_, favcat) => ({ favcat, name: "" }));
  return source.map((folder) => ({
    value: String(folder.favcat),
    label: folder.name ? `${folder.name} #${folder.favcat}` : `#${folder.favcat}`,
  }));
});

/* -------------------------------------------------------------- filter model */

const listOptions = computed<Array<{ value: OnlineListType; label: string }>>(() => [
  { value: "search", label: t("online.list.search") },
  { value: "popular", label: t("online.list.popular") },
  { value: "watched", label: t("online.list.watched") },
  { value: "toplist", label: t("online.list.toplist") },
]);

const toplistOptions = [
  { value: "11", label: t("online.toplist.11") },
  { value: "12", label: t("online.toplist.12") },
  { value: "13", label: t("online.toplist.13") },
  { value: "15", label: t("online.toplist.15") },
];

const ratingOptions = computed(() => [
  { value: "", label: t("online.ratingAny") },
  ...["2", "3", "4", "5"].map((value) => ({
    value,
    label: t("online.ratingAtLeast", { value }),
  })),
]);

const minRatingValue = computed({
  get: () => (filters.min_rating === null ? "" : String(filters.min_rating)),
  set: (value: string) => {
    apply({ min_rating: value ? Number(value) : null });
  },
});

const selectedCats = computed(() => new Set(enabledCategories(filters.category)));
const allSelected = computed(() => filters.category === 0);

const activeFilterCount = computed(
  () =>
    (filters.category > 0 ? 1 : 0) +
    (filters.min_rating !== null ? 1 : 0) +
    (filters.list !== "search" ? 1 : 0),
);

function categoryChipStyle(name: OnlineCategory): Record<string, string> {
  const token = categoryToken(name);
  return {
    "--chip-bg": `var(${token})`,
    "--chip-ink": `var(${token}-ink)`,
  };
}

function categoryLabel(name: OnlineCategory): string {
  return t(`online.categories.${name}`);
}

/* --------------------------------------------------------------- card model */

const cards = computed<GalleryItem[]>(() =>
  store.items.map((item) => {
    const favorite = favorites.entries[item.gid];
    const download = downloads.entries[item.gid];
    const tags = (item.tags ?? []).map((tag) => ({
      namespace: tag.namespace,
      name: tag.name,
      display: tag.display ?? null,
    }));
    return {
      id: item.gid,
      gid: item.gid,
      token: item.token,
      title: item.title,
      category: item.category,
      page_count: item.pages,
      cover_url: item.thumb ?? null,
      tags,
      tag_count: tags.length,
      uploader: item.uploader?.trim() || null,
      posted_at: normalizePosted(item.posted),
      file_size: null,
      rating: item.rating ?? null,
      // Store state wins so favourites / downloads stay in sync across the
      // card, detail and reader without a list refetch.
      favorite: favorite ? favorite.favorited : Boolean(item.favorited),
      favorite_category: favorite ? favorite.favcat : (item.favcat ?? null),
      in_library: download ? download.inLibrary : Boolean(item.in_library),
      download_status:
        download && download.status !== "idle" ? download.status : (item.download_status ?? null),
    };
  }),
);

/** Table rows already have separate columns; drop language from their chips. */
const collectionItems = computed<GalleryItem[]>(() => {
  if (view.mode.value !== "table") return cards.value;
  return cards.value.map((card) => {
    const tags = withoutLanguageTags(card.tags);
    return { ...card, tags, tag_count: tags.length };
  });
});

function isSelected(id: number): boolean {
  return selected.value.includes(id);
}

function onSelect(id: number, next: boolean): void {
  if (next) {
    if (!isSelected(id)) selected.value = [...selected.value, id];
    return;
  }
  selected.value = selected.value.filter((value) => value !== id);
}

function selectAllLoaded(): void {
  selected.value = cards.value
    .filter((card) => card.token)
    .map((card) => card.gid ?? card.id);
}

function clearSelection(): void {
  selected.value = [];
}

function selectedCards(): GalleryItem[] {
  const chosen = new Set(selected.value);
  return cards.value.filter((card) => card.gid !== null && chosen.has(card.gid) && card.token);
}

/* ------------------------------------------------------------------- tags */

function tagFromChip(chip: HTMLElement): TagLike | null {
  const label = chip.getAttribute("aria-label") ?? chip.getAttribute("title") ?? "";
  const marker = label.lastIndexOf("：");
  const raw = (marker >= 0 ? label.slice(marker + 1) : label).trim();
  const separator = raw.indexOf(":");
  if (separator <= 0) return null;
  return { namespace: raw.slice(0, separator), name: raw.slice(separator + 1) };
}

function onTagSelect(tag: TagLike): void {
  const next = appendEhTagQuery(term.value || filters.q, tag);
  term.value = next;
  apply({ q: next });
}

/**
 * Grid cards and table rows are shared collection components whose tag chips
 * navigate with a replaced `q`. Capture the click before their handler so the
 * page keeps the "append" contract for all three views.
 */
function onTagClickCapture(event: MouseEvent): void {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const chip = target.closest<HTMLElement>(".tag-chip");
  if (!chip || chip.closest(".online-row")) return;
  const tag = tagFromChip(chip);
  if (!tag) return;
  event.preventDefault();
  event.stopPropagation();
  onTagSelect(tag);
}

/* --------------------------------------------------------------- navigation */

function routeFilters(): OnlineFilters {
  const fromQuery = parseFiltersFromQuery(route.query);
  const base = hasFilterQuery(route.query) ? DEFAULT_ONLINE_FILTERS : loadOnlineDefaults();
  return normalizeFilters({ ...base, ...fromQuery });
}

function assignFilters(next: OnlineFilters): void {
  filters.q = next.q;
  filters.category = next.category;
  filters.min_rating = next.min_rating;
  filters.list = next.list;
  filters.tl = next.tl;
  term.value = next.q;
}

function sameQuery(target: Record<string, string>): boolean {
  for (const key of Object.keys(target)) {
    const current = route.query[key];
    if (String(Array.isArray(current) ? current[0] : (current ?? "")) !== target[key]) return false;
  }
  for (const key of Object.keys(route.query)) {
    if (!(key in target) && route.query[key] !== undefined) return false;
  }
  return true;
}

function restoreScrollSoon(): void {
  const target = store.savedScroll();
  if (target <= 0) return;
  void nextTick(() => {
    window.requestAnimationFrame(() => window.scrollTo(0, target));
  });
}

function startWith(next: OnlineFilters): void {
  const resumed = store.start(next);
  if (resumed) restoreScrollSoon();
}

function apply(custom?: Partial<OnlineFilters>): void {
  const next = normalizeFilters({ ...filters, ...custom });
  saveOnlineDefaults(next);
  assignFilters(next);
  const target = filtersToQuery(next);
  if (!sameQuery(target)) {
    void router.push({ name: "online", query: target });
    return;
  }
  startWith(next);
}

function submit(): void {
  apply({ q: term.value });
}

function reset(): void {
  term.value = "";
  filtersOpen.value = true;
  apply({ ...DEFAULT_ONLINE_FILTERS });
}

function setList(list: OnlineListType): void {
  apply({ list, tl: list === "toplist" ? filters.tl : 15 });
}

function onToplist(value: string): void {
  apply({ tl: Number(value) });
}

function toggleCat(name: OnlineCategory): void {
  apply({ category: toggleCategory(filters.category, name) });
}

function selectAllCats(): void {
  apply({ category: 0 });
}

/* --------------------------------------------------------------- batch ops */

async function batchDownload(): Promise<void> {
  if (batchBusy.value) return;
  const picked = selectedCards();
  if (!picked.length) {
    ui.info(t("legacy.select"));
    return;
  }
  batchBusy.value = true;
  try {
    const result = await createDownloadsBatch({
      items: picked.map((card) => ({
        gid: card.gid as number,
        token: card.token as string,
        title: card.title,
      })),
      quality: readDefaultQuality(),
    });
    for (const item of result.items) {
      if (!item.gid) continue;
      if (item.status === "queued" || item.status === "updated") {
        downloads.applySeed(item.gid, { status: "queued" });
        downloads.watch(item.gid);
      }
    }
    const parts = [t("legacy.dlQueuedCount", { count: result.queued })];
    if (result.skipped) parts.push(t("legacy.dlSkippedCount", { count: result.skipped }));
    if (result.gone) parts.push(t("legacy.dlGone"));
    if (result.failed) parts.push(t("legacy.dlFailedCount", { count: result.failed }));
    ui.success(parts.join(" · "));
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.discoverError"));
  } finally {
    batchBusy.value = false;
  }
}

async function openBatchFavorite(): Promise<void> {
  if (!selectedCards().length) {
    ui.info(t("legacy.select"));
    return;
  }
  batchFavoriteOpen.value = true;
  if (!favoriteCategories.value.length) {
    try {
      favoriteCategories.value = await favorites.loadCategories();
    } catch {
      favoriteCategories.value = [];
    }
  }
  if (!favoriteOptions.value.some((option) => option.value === favoriteTarget.value)) {
    favoriteTarget.value = favoriteOptions.value[0]?.value ?? "0";
  }
}

async function submitBatchFavorite(): Promise<void> {
  if (batchBusy.value) return;
  const picked = selectedCards();
  if (!picked.length) {
    ui.info(t("legacy.select"));
    return;
  }
  const target = Number.parseInt(favoriteTarget.value, 10);
  if (!Number.isInteger(target) || target < 0 || target > 9) return;
  batchBusy.value = true;
  try {
    const result = await addFavoritesBatch(
      picked.map((card) => ({
        gid: card.gid as number,
        token: card.token as string,
        title: card.title,
      })),
      target,
    );
    // Cloud-first: only gids confirmed by the backend update the heart state.
    for (const gid of result.successful_gids) {
      favorites.applyFavorite(gid, target);
    }
    ui.success(
      t("legacy.favAddBatch", {
        count: result.successful_gids.length || result.local_added || 0,
        failed: result.cloud_failed.length,
      }),
    );
    batchFavoriteOpen.value = false;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : t("legacy.favAddFail"));
  } finally {
    batchBusy.value = false;
  }
}

/* ------------------------------------------------------------------ watchers */

watch(
  () => route.query,
  () => {
    const next = routeFilters();
    assignFilters(next);
    startWith(next);
  },
  { immediate: true, deep: true },
);

// Filter/list changes start a new selection scope (legacy `selectionScopeChanged`).
watch(
  () => store.currentKey,
  (key, previous) => {
    if (previous && key !== previous) selected.value = [];
  },
);

onMounted(() => {
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    media = window.matchMedia("(max-width: 599px)");
    syncCompact();
    media.addEventListener?.("change", syncCompact);
  }
  if (store.items.length > 0) restoreScrollSoon();
});

onBeforeRouteLeave(() => {
  store.saveScroll(window.scrollY);
  selected.value = [];
});

onBeforeUnmount(() => {
  media?.removeEventListener?.("change", syncCompact);
  store.saveScroll(window.scrollY);
});
</script>

<template>
  <section class="online" data-testid="online-view" @click.capture="onTagClickCapture">
    <PageHeader
      :title="t('online.title')"
      :subtitle="t('online.subtitle')"
      testid="online-header"
    />

    <form class="online__search-form" role="search" @submit.prevent="submit">
      <Toolbar testid="online-toolbar">
        <Input
          v-model="term"
          class="online__search"
          icon="search"
          :placeholder="t('online.searchPlaceholder')"
          :aria-label="t('online.searchLabel')"
          :clear-label="t('online.clearSearch')"
          clearable
          data-testid="online-search"
          @enter="submit"
        />
        <Button type="submit" variant="filled" data-testid="online-submit">
          {{ t("online.search") }}
        </Button>
        <ToolbarGroup end>
          <FilterButton
            :count="activeFilterCount"
            :label="t('online.filter')"
            :aria-expanded="filtersOpen"
            data-testid="online-filter-button"
            @click="filtersOpen = !filtersOpen"
          />
          <ViewModeToggle
            :model-value="view.mode.value"
            :options="view.available.value"
            @update:model-value="view.setMode"
          />
        </ToolbarGroup>
      </Toolbar>
    </form>

    <div
      v-show="filtersOpen"
      class="online__filters"
      role="group"
      :aria-label="t('online.filtersLabel')"
      data-testid="online-filters-row"
    >
      <SegmentedControl
        :model-value="filters.list"
        :options="listOptions"
        :label="t('online.listLabel')"
        size="sm"
        testid="online-list-types"
        @change="(value: string) => setList(value as OnlineListType)"
      />
      <Select
        class="online__select"
        size="sm"
        :model-value="minRatingValue"
        :options="ratingOptions"
        :aria-label="t('online.minRating')"
        data-testid="online-min-rating"
        @update:model-value="(value: string) => apply({ min_rating: value ? Number(value) : null })"
      />
      <Select
        v-if="filters.list === 'toplist'"
        class="online__select"
        size="sm"
        :model-value="String(filters.tl)"
        :options="toplistOptions"
        :aria-label="t('online.toplist.label')"
        data-testid="online-toplists"
        @update:model-value="onToplist"
      />
      <Chip
        class="online__cat-chip"
        :label="t('online.categoriesAll')"
        :selected="allSelected"
        data-testid="online-cat-all"
        @click="selectAllCats"
      />
      <Chip
        v-for="name in ONLINE_CATEGORIES"
        :key="name"
        class="online__cat-chip"
        :label="categoryLabel(name)"
        :selected="selectedCats.has(name)"
        :style="categoryChipStyle(name)"
        :data-testid="`online-cat-${name}`"
        @click="toggleCat(name)"
      />
    </div>

    <p v-if="filters.category > 0" class="online__mask" data-testid="online-mask">
      {{ t("online.mask", { mask: filters.category }) }}
    </p>

    <SelectionBar
      v-if="selectedCount > 0"
      testid="online-selected-count"
      :count="selectedCount"
      :label="t('online.selectedCount', { count: selectedCount })"
      :clear-label="t('online.clearSelection')"
      @clear="clearSelection"
    >
      <Button variant="outlined" data-testid="online-select-all" @click="selectAllLoaded">
        {{ t("legacy.selectAll") }}
      </Button>
      <Button
        variant="outlined"
        :loading="batchBusy"
        data-testid="online-batch-download"
        @click="batchDownload"
      >
        {{ t("legacy.discoverBatchDl") }}{{ selectedCount ? ` (${selectedCount})` : "" }}
      </Button>
      <Button
        variant="outlined"
        :disabled="batchBusy"
        data-testid="online-batch-favorite"
        @click="openBatchFavorite"
      >
        {{ t("legacy.discoverBatchFav") }}{{ selectedCount ? ` (${selectedCount})` : "" }}
      </Button>
    </SelectionBar>

    <div v-if="store.initialLoading" class="online__skeletons" aria-hidden="true">
      <Skeleton v-for="index in skeletonCount" :key="index" variant="list" />
    </div>

    <ErrorState
      v-else-if="store.error && store.items.length === 0"
      :title="t('online.loadFailed')"
      :body="store.error"
      :retry-label="t('online.retry')"
      testid="online-error"
      @retry="store.retry"
    />

    <OnlineStateNotice
      v-else-if="store.state !== 'ok' && store.state !== 'empty'"
      :state="store.state"
      @retry="store.retry"
    />

    <template v-else-if="store.state === 'empty' || (store.items.length === 0 && !store.loading)">
      <GalleryCollection
        v-if="view.mode.value === 'table'"
        :items="[]"
        mode="table"
        :columns="ONLINE_TABLE_COLUMNS"
        source="online"
        testid="online-grid"
      />
      <EmptyState
        :title="t('online.emptyTitle')"
        :body="t('online.emptyBody')"
        :action-label="t('online.reset')"
        testid="online-empty"
        @action="reset"
      />
    </template>

    <GalleryCollection
      v-else
      :items="collectionItems"
      :mode="view.mode.value"
      :columns="ONLINE_TABLE_COLUMNS"
      source="online"
      :selectable="true"
      :selected="selected"
      :loading="store.loading"
      :has-more="store.hasMore"
      :error="store.error"
      :total="store.items.length"
      testid="online-grid"
      @load-more="store.loadMore"
      @retry="store.retry"
      @select="onSelect"
    >
      <template #card="{ item }">
        <div class="online__card" data-testid="online-card" :data-gid="item.gid">
          <OnlineListRow
            v-if="view.mode.value === 'list'"
            :item="item"
            :selected="isSelected(item.id)"
            :tag-max="tagMax"
            @select="onSelect"
            @tag="onTagSelect"
          />
          <GalleryCard
            v-else
            :item="item"
            variant="grid"
            source="online"
            :selectable="true"
            :selected="isSelected(item.id)"
            @select="onSelect"
          />
        </div>
      </template>
    </GalleryCollection>

    <Dialog
      :open="batchFavoriteOpen"
      :title="t('legacy.favAddTitle')"
      testid="online-batch-favorite-dialog"
      @close="batchFavoriteOpen = false"
    >
      <div class="online__favorite-form">
        <p class="online__favorite-count">
          {{ t("online.selectedCount", { count: selectedCount }) }}
        </p>
        <Select
          :model-value="favoriteTarget"
          :options="favoriteOptions"
          :label="t('legacy.favMoveTarget')"
          data-testid="online-batch-favorite-target"
          @update:model-value="favoriteTarget = $event"
        />
      </div>
      <template #footer>
        <Button variant="text" type="button" @click="batchFavoriteOpen = false">
          {{ t("legacy.cancel") }}
        </Button>
        <Button
          type="button"
          :loading="batchBusy"
          data-testid="online-batch-favorite-confirm"
          @click="submitBatchFavorite"
        >
          {{ t("legacy.favAddConfirm") }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.online {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.online__search-form {
  display: block;
  width: 100%;
}

.online__search {
  flex: 1 1 240px;
  min-width: 180px;
}

.online__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.online__select {
  flex: none;
  width: 150px;
}

/* Category chips keep the per-category colour from --gv-cat-* (DESIGN C05). */
.online__filters :deep(.chip--selected) {
  border-color: transparent;
  background: var(--chip-bg, var(--gv-color-secondary-container));
  color: var(--chip-ink, var(--gv-color-on-secondary-container));
}

.online__mask {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.online__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.online__card {
  height: 100%;
  min-width: 0;
}

.online__favorite-form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.online__favorite-count {
  margin: 0;
}

@media (max-width: 599.98px) {
  .online__search {
    flex: 1 1 100%;
    min-width: 0;
  }

  .online__select {
    width: 132px;
  }
}

@media (min-width: 840px) {
  .online {
    gap: var(--gv-space-5);
  }
}
</style>
