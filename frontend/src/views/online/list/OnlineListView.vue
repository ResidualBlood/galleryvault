<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import VirtualGrid from "@/components/gallery/VirtualGrid.vue";
import GalleryCard from "@/components/gallery/GalleryCard.vue";
import GalleryActions from "@/components/actions/GalleryActions.vue";
import type { GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
import type { GalleryItem } from "@/api/library";
import type { OnlineListType } from "@/api/eh";
import { createDownloadsBatch } from "@/api/downloads";
import {
  addFavoritesBatch,
  type FavoriteCategory,
} from "@/api/favorites";
import { useFavoritesStore } from "@/stores/favorites";
import { readDefaultQuality, useDownloadsStore } from "@/stores/downloads";
import { useUiStore } from "@/stores/ui";
import {
  DEFAULT_ONLINE_FILTERS,
  ONLINE_CATEGORIES,
  enabledCategories,
  filtersToQuery,
  hasFilterQuery,
  loadOnlineDefaults,
  mergeDownloadBadge,
  normalizeFilters,
  parseFiltersFromQuery,
  saveOnlineDefaults,
  toggleCategory,
  useOnlineStore,
  type OnlineCategory,
  type OnlineFilters,
} from "@/stores/online";
import OnlineStateNotice from "./OnlineStateNotice.vue";
import { categoryBadge, categoryToken } from "./category";
import { ensureOnlineMessages } from "./messages";

ensureOnlineMessages();

const route = useRoute();
const router = useRouter();
const store = useOnlineStore();
const favorites = useFavoritesStore();
const downloads = useDownloadsStore();
const ui = useUiStore();
const { t } = useI18n();

const filters = reactive<OnlineFilters>({ ...DEFAULT_ONLINE_FILTERS });
const term = ref("");
const skeletonCount = 6;

/* --------------------------------------------------------- batch selection */

/** Legacy `selDiscover`: gids survive infinite-scroll appends but reset when
 * the filter scope or the route changes. */
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
    filters.min_rating = value ? Number(value) : null;
  },
});

const selectedCats = computed(() => new Set(enabledCategories(filters.category)));

type OnlineCard = GalleryItem & { gid: number; token: string };

const cards = computed<OnlineCard[]>(() =>
  store.items.map((item) => {
    const favorite = favorites.entries[item.gid];
    const download = downloads.entries[item.gid];
    return {
      id: item.gid,
      gid: item.gid,
      token: item.token,
      title: item.title,
      category: item.category,
      page_count: item.pages,
      cover_url: item.thumb ?? null,
      tags: [],
      uploader: null,
      posted_at: null,
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

function badgesFor(card: GalleryItem): GalleryBadge[] {
  return buildBadges(card);
}

function buildBadges(card: GalleryItem): GalleryBadge[] {
  const badges: GalleryBadge[] = [
    categoryBadge(card.category, t(`online.categories.${card.category}`, t("online.categories.misc"))),
  ];
  if (card.in_library) {
    badges.push({ label: t("online.badges.inLibrary"), tone: "success" });
  }
  const download = mergeDownloadBadge(card.download_status);
  if (download) {
    const label =
      download.key === "downloading"
        ? t("online.badges.downloading")
        : download.key === "queued"
          ? t("online.badges.queued")
          : t("online.badges.failed");
    badges.push({ label, tone: download.tone });
  } else if (card.favorite) {
    badges.push({ label: "♥", tone: "primary", title: t("online.badges.favorited") });
  }
  return badges;
}

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

/** Card quick action: jump straight into the online reader at page 1. */
function readFromCard(card: GalleryItem): void {
  if (!card.gid || !card.token) return;
  void router.push({
    name: "online-reader",
    params: { gid: card.gid, token: card.token, page: 0 },
  });
}

function isSelected(gid: number): boolean {
  return selected.value.includes(gid);
}

function toggleSelection(gid: number, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
  if (checked) {
    if (!isSelected(gid)) selected.value = [...selected.value, gid];
  } else {
    selected.value = selected.value.filter((value) => value !== gid);
  }
}

function selectAllLoaded(): void {
  selected.value = cards.value.map((card) => card.gid);
}

function clearSelection(): void {
  selected.value = [];
}

function selectedCards(): OnlineCard[] {
  const chosen = new Set(selected.value);
  return cards.value.filter((card) => chosen.has(card.gid) && card.token);
}

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
        gid: card.gid,
        token: card.token,
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
      picked.map((card) => ({ gid: card.gid, token: card.token, title: card.title })),
      target,
    );
    // Cloud-first: only gids confirmed by the backend update the ♥ badge.
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
    if (String(Array.isArray(current) ? current[0] : current ?? "") !== target[key]) return false;
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

const allSelected = computed(() => filters.category === 0);

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
  if (store.items.length > 0) restoreScrollSoon();
});

onBeforeRouteLeave(() => {
  store.saveScroll(window.scrollY);
  selected.value = [];
});

onBeforeUnmount(() => {
  store.saveScroll(window.scrollY);
});
</script>

<template>
  <section class="online" data-testid="online-view">
    <header class="online__header">
      <p class="online__eyebrow">EXHENTAI</p>
      <h1 class="online__title">{{ t("online.title") }}</h1>
      <p class="online__subtitle">{{ t("online.subtitle") }}</p>
    </header>

    <form class="online__toolbar" data-testid="online-filters" @submit.prevent="submit">
      <div class="online__row">
        <Input
          v-model="term"
          class="online__search"
          :label="t('online.searchLabel')"
          :placeholder="t('online.searchPlaceholder')"
          data-testid="online-search"
          @enter="submit"
        />
        <Button type="submit" variant="filled" data-testid="online-submit">
          {{ t("online.search") }}
        </Button>
        <Button type="button" variant="text" data-testid="online-reset" @click="reset">
          {{ t("online.reset") }}
        </Button>
      </div>

      <div class="online__row" role="group" :aria-label="t('online.listLabel')">
        <Button
          v-for="option in listOptions"
          :key="option.value"
          type="button"
          :variant="filters.list === option.value ? 'filled' : 'outlined'"
          size="compact"
          :data-testid="`online-list-${option.value}`"
          :aria-pressed="filters.list === option.value"
          @click="setList(option.value)"
        >
          {{ option.label }}
        </Button>
        <Select
          v-if="filters.list === 'toplist'"
          class="online__select"
          :model-value="String(filters.tl)"
          :label="t('online.toplist.label')"
          :options="toplistOptions"
          data-testid="online-toplists"
          @update:model-value="onToplist"
        />
        <Select
          class="online__select"
          :model-value="minRatingValue"
          :label="t('online.minRating')"
          :options="ratingOptions"
          data-testid="online-min-rating"
          @update:model-value="(value: string) => apply({ min_rating: value ? Number(value) : null })"
        />
      </div>

      <div class="online__cats" role="group" :aria-label="t('online.categoriesLabel')">
        <span class="online__cats-label">{{ t("online.categoriesLabel") }}</span>
        <button
          type="button"
          class="cat-chip cat-chip--all"
          :class="{ 'cat-chip--on': allSelected }"
          :aria-pressed="allSelected"
          data-testid="online-cat-all"
          @click="selectAllCats"
        >
          {{ t("online.categoriesAll") }}
        </button>
        <button
          v-for="name in ONLINE_CATEGORIES"
          :key="name"
          type="button"
          class="cat-chip"
          :class="{ 'cat-chip--on': selectedCats.has(name) }"
          :style="categoryChipStyle(name)"
          :aria-pressed="selectedCats.has(name)"
          :data-testid="`online-cat-${name}`"
          @click="toggleCat(name)"
        >
          {{ categoryLabel(name) }}
        </button>
      </div>

      <div class="online__row online__batch" role="group" :aria-label="t('legacy.discover')">
        <span class="online__selected" data-testid="online-selected-count">
          {{ t("online.selectedCount", { count: selectedCount }) }}
        </span>
        <Button
          type="button"
          variant="outlined"
          size="compact"
          data-testid="online-select-all"
          @click="selectAllLoaded"
        >
          {{ t("legacy.selectAll") }}
        </Button>
        <Button
          type="button"
          variant="text"
          size="compact"
          data-testid="online-clear-selection"
          @click="clearSelection"
        >
          {{ t("legacy.clearSel") }}
        </Button>
        <Button
          type="button"
          variant="outlined"
          size="compact"
          :loading="batchBusy"
          data-testid="online-batch-download"
          @click="batchDownload"
        >
          {{ t("legacy.discoverBatchDl") }}{{ selectedCount ? ` (${selectedCount})` : "" }}
        </Button>
        <Button
          type="button"
          variant="outlined"
          size="compact"
          :disabled="batchBusy"
          data-testid="online-batch-favorite"
          @click="openBatchFavorite"
        >
          {{ t("legacy.discoverBatchFav") }}{{ selectedCount ? ` (${selectedCount})` : "" }}
        </Button>
      </div>
    </form>

    <p v-if="filters.category > 0" class="online__mask" data-testid="online-mask">
      {{ t("online.mask", { mask: filters.category }) }}
    </p>

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

    <EmptyState
      v-else-if="store.state === 'empty' || (store.items.length === 0 && !store.loading)"
      :title="t('online.emptyTitle')"
      :body="t('online.emptyBody')"
      testid="online-empty"
    />

    <VirtualGrid
      v-else
      :items="cards"
      :loading="store.loading"
      :has-more="store.hasMore"
      :error="store.error"
      :total="store.items.length"
      variant="list"
      source="online"
      testid="online-grid"
      @load-more="store.loadMore"
      @retry="store.retry"
    >
      <template #card="{ item }">
        <div
          class="online-card"
          :class="{ 'online-card--selected': isSelected(item.gid ?? 0) }"
          data-testid="online-card"
          :data-gid="item.gid"
        >
          <label class="online-card__check" :title="t('legacy.select')">
            <input
              type="checkbox"
              :checked="isSelected(item.gid ?? 0)"
              :aria-label="t('online.selectItem', { title: item.title })"
              :data-gid="item.gid"
              @change="toggleSelection(item.gid ?? 0, $event)"
            />
          </label>
          <GalleryCard
            :item="item"
            variant="list"
            source="online"
            :badges="badgesFor(item)"
          >
            <template #actions>
              <GalleryActions
                v-if="item.gid && item.token"
                :gid="item.gid"
                :token="item.token"
                :title="item.title"
                source="online"
                density="card"
                :favorited="Boolean(item.favorite)"
                :favcat="item.favorite_category ?? null"
                :in-library="Boolean(item.in_library)"
                :download-status="item.download_status ?? null"
                @read="readFromCard(item)"
              />
            </template>
          </GalleryCard>
        </div>
      </template>
    </VirtualGrid>

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

.online__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.online__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.online__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.online__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.online__toolbar {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
}

.online__row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.online__search {
  flex: 1 1 240px;
  min-width: 200px;
}

.online__select {
  min-width: 132px;
}

.online__cats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.online__cats-label {
  margin-right: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-medium);
}

.online__batch {
  align-items: center;
  padding-top: var(--gv-space-2);
  border-top: 1px solid var(--gv-color-outline-variant);
}

.online__selected {
  margin-right: auto;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-medium);
}

.online__favorite-form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.online__favorite-count {
  margin: 0;
}

.online-card {
  position: relative;
  height: 100%;
}

.online-card__check {
  position: absolute;
  top: var(--gv-space-2);
  right: var(--gv-space-2);
  z-index: 3;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, var(--gv-color-surface) 82%, transparent);
  box-shadow: var(--gv-elev-1);
  cursor: pointer;
}

.online-card__check input {
  width: 18px;
  height: 18px;
  accent-color: var(--gv-color-primary);
  cursor: pointer;
}

.online-card--selected :deep(.gallery-card) {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

.cat-chip {
  height: 24px;
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  cursor: pointer;
}

.cat-chip--on {
  border-color: var(--gv-color-primary);
  background: var(--chip-bg, var(--gv-color-secondary-container));
  color: var(--chip-ink, var(--gv-color-on-secondary-container));
  box-shadow: inset 0 0 0 1px var(--gv-color-primary);
}

.cat-chip--all.cat-chip--on {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.cat-chip:hover {
  background: var(--gv-color-surface-container-highest);
}

.cat-chip:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
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

@media (min-width: 840px) {
  .online {
    gap: var(--gv-space-5);
  }

  .online__toolbar {
    padding: var(--gv-space-4);
  }
}
</style>
