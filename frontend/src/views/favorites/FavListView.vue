<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import ArchiveDialog from "@/components/system/ArchiveDialog.vue";
import { PAGE_SIZES, clampPageSize, formatBytes } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
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
import {
  activeFavFilterCount,
  buildFavListParams,
  emptyFavListFilters,
  favListQuery,
  filtersFromQuery,
  type FavListFilters,
} from "./filters";
import { ensureFavoritesMessages } from "./messages";

ensureFavoritesMessages();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();

const favcat = computed(() => {
  const parsed = Number.parseInt(String(route.params.id ?? ""), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
});

const filters = ref<FavListFilters>(emptyFavListFilters(settings.pageSize));
const advancedOpen = ref(false);
const items = ref<FavoriteItem[]>([]);
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

const folderName = computed(() => {
  const folder = categories.value.find((item) => item.favcat === favcat.value);
  return folder?.name?.trim() || `#${favcat.value}`;
});

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
  ...[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: `≥ ${value} ★` })),
]);

const pageSizeOptions = computed(() => {
  const values = new Set(PAGE_SIZES.map(String));
  values.add(String(settings.pageSize));
  values.add(String(filters.value.page_size));
  return [...values]
    .map(Number)
    .sort((a, b) => a - b)
    .map((value) => ({ value: String(value), label: String(value) }));
});

const moveOptions = computed(() =>
  categories.value
    .filter((item) => item.favcat !== favcat.value)
    .map((item) => ({
      value: String(item.favcat),
      label: item.name ? `${item.name} #${item.favcat}` : `#${item.favcat}`,
    })),
);

const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / Math.max(1, filters.value.page_size))),
);

const pageLinks = computed(() => {
  const current = filters.value.page;
  const last = pageCount.value;
  const start = Math.max(1, current - 2);
  const end = Math.min(last, current + 2);
  const pages: number[] = [];
  for (let page = start; page <= end; page += 1) pages.push(page);
  return pages;
});

const activeTagList = computed(() =>
  filters.value.tags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean),
);

const advancedCount = computed(() => activeFavFilterCount(filters.value));
const allLoaded = computed(() => items.value.length >= total.value);
const hasSelection = computed(() => selected.value.length > 0);

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

function tagLabel(tag: FavoriteItem["tags"][number]): string {
  if (tag.display) return tag.display;
  return tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name;
}

function tagKey(tag: FavoriteItem["tags"][number]): string {
  return tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name;
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
    items.value = data.items;
    total.value = data.total;
    loadedPage.value = page;
  } catch (cause) {
    if (seq !== requestSeq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
    items.value = [];
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
    const known = new Set(items.value.map((item) => item.gid));
    items.value = [
      ...items.value,
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

function setState(state: FavListFilters["state"]): void {
  filters.value.state = state;
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function clearFilters(): void {
  filters.value = emptyFavListFilters(settings.pageSize);
  advancedOpen.value = false;
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function onPageSize(value: string): void {
  const next = clampPageSize(value, settings.pageSize);
  settings.setPageSize(next);
  filters.value.page_size = next;
  const query = withFrom(favListQuery({ ...filters.value, page: 1 }));
  void router.push({ name: "favorites-list", params: { id: favcat.value }, query });
}

function applyTag(tag: FavoriteItem["tags"][number]): void {
  const key = tagKey(tag);
  if (!key) return;
  const parts = activeTagList.value;
  if (!parts.some((item) => item.toLowerCase() === key.toLowerCase())) {
    filters.value.tags = [...parts, key].join(",");
  }
  applyFilters();
}

function removeTag(tag: string): void {
  filters.value.tags = activeTagList.value.filter((item) => item !== tag).join(",");
  applyFilters();
}

function isSelected(gid: number): boolean {
  return selected.value.includes(gid);
}

function onSelect(gid: number, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
  if (checked && !isSelected(gid)) selected.value = [...selected.value, gid];
  if (!checked) selected.value = selected.value.filter((value) => value !== gid);
}

function selectAllLoaded(): void {
  selected.value = items.value.map((item) => item.gid);
}

function clearSelection(): void {
  selected.value = [];
}

/** Legacy favorites.js `checkFavoriteCategory(favcat)`: start one folder scan. */
async function checkFolder(): Promise<void> {
  if (checking.value) return;
  checking.value = true;
  try {
    await checkFavoriteCategory(favcat.value);
    ui.success(
      `${t("favorites.list.checkFolderStarted")} #${favcat.value}${folderName.value ? ` · ${folderName.value}` : ""}`,
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
  if (!hasSelection.value) {
    ui.info(t("legacy.select"));
    return;
  }
  moveTarget.value = moveOptions.value[0]?.value ?? "";
  dialog.value = "move";
}

function openRemove(): void {
  if (!hasSelection.value) {
    ui.info(t("legacy.select"));
    return;
  }
  dialog.value = "remove";
}

function openArchive(): void {
  if (!hasSelection.value) {
    ui.info(t("legacy.select"));
    return;
  }
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
    <div class="favlist__back">
      <RouterLink class="favlist__back-link" to="/favorites">
        ← {{ t("legacy.favorites") }}
      </RouterLink>
      <RouterLink
        v-if="first(route.query.from)"
        class="favlist__back-link"
        :to="`/gallery/${first(route.query.from)}`"
      >
        ← {{ t("legacy.backToGallery") }}
      </RouterLink>
    </div>

    <header class="favlist__header">
      <p class="favlist__eyebrow">{{ t("favorites.list.eyebrow") }}</p>
      <h1 class="favlist__title">
        {{ folderName }}
        <span class="favlist__cat">#{{ favcat }}</span>
      </h1>
      <p class="favlist__subtitle">
        {{ t("legacy.favListSub") }}
        <span v-if="total">· {{ t("favorites.list.total", { n: total }) }}</span>
      </p>
    </header>

    <form class="favlist__search" role="search" @submit.prevent="applyFilters">
      <Input
        v-model="filters.q"
        class="favlist__search-input"
        :label="t('legacy.search')"
        :placeholder="t('legacy.favSearchPlaceholder')"
        data-testid="favlist-q"
      />
      <Select
        v-model="filters.category"
        class="favlist__select"
        :options="categoryOptions"
        :label="t('legacy.allCategories')"
        data-testid="favlist-category"
      />
      <Select
        v-model="filters.language"
        class="favlist__select"
        :options="languageOptions"
        :label="t('favorites.list.language')"
        data-testid="favlist-language"
      />
      <Button type="submit">{{ t("legacy.search") }}</Button>
      <Button variant="text" type="button" data-testid="favlist-clear" @click="clearFilters">
        {{ t("favorites.list.clearFilters") }}
      </Button>
    </form>

    <div class="favlist__advanced-head">
      <button
        type="button"
        class="favlist__advanced-toggle"
        :aria-expanded="advancedOpen"
        data-testid="favlist-advanced-toggle"
        @click="advancedOpen = !advancedOpen"
      >
        {{ t("legacy.library_filters_advanced") }}
        <span v-if="advancedCount" class="favlist__advanced-count">
          {{ t("legacy.library_filters_activeCount", { n: advancedCount }) }}
        </span>
      </button>
    </div>

    <div v-if="advancedOpen" class="favlist__advanced" data-testid="favlist-advanced">
      <Select
        v-model="filters.order_by"
        :options="orderOptions"
        :label="t('legacy.orderRating')"
        data-testid="favlist-order"
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
      <div class="favlist__range">
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
      </div>
      <div class="favlist__range">
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
      </div>
      <div class="favlist__range">
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
      </div>
      <Input
        v-model="filters.uploader"
        :label="t('legacy.uploader')"
        data-testid="favlist-uploader"
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
      <Button type="button" variant="tonal" @click="applyFilters">
        {{ t("legacy.applySearch") }}
      </Button>
    </div>

    <div v-if="activeTagList.length" class="favlist__tags">
      <span v-for="tag in activeTagList" :key="tag" class="favlist__tag">
        {{ tag }}
        <button
          type="button"
          class="favlist__tag-remove"
          :aria-label="t('legacy.clearSel') + ' ' + tag"
          @click="removeTag(tag)"
        >
          ×
        </button>
      </span>
    </div>

    <div class="favlist__toolbar">
      <div class="favlist__states" role="group" :aria-label="t('favorites.list.stateLabel')">
        <button
          v-for="state in (['all', 'local', 'cloud'] as const)"
          :key="state"
          type="button"
          class="favlist__state"
          :class="{ 'favlist__state--active': filters.state === state }"
          :aria-pressed="filters.state === state"
          @click="setState(state)"
        >
          {{ t(`legacy.favState${state === "all" ? "All" : state === "local" ? "Local" : "Cloud"}`) }}
        </button>
      </div>
      <Button
        variant="outlined"
        size="compact"
        type="button"
        :loading="checking"
        data-testid="favlist-check"
        @click="checkFolder"
      >
        {{ t("favorites.list.checkFolder") }}
      </Button>
      <Button variant="outlined" size="compact" type="button" @click="selectAllLoaded">
        {{ t("legacy.selectAll") }}
      </Button>
      <Button variant="outlined" size="compact" type="button" @click="clearSelection">
        {{ t("legacy.clearSel") }}
      </Button>
      <Button
        size="compact"
        type="button"
        :loading="busy"
        data-testid="favlist-download"
        @click="queueSelected()"
      >
        {{ t("legacy.favDl") }}{{ hasSelection ? ` (${selected.length})` : "" }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        type="button"
        data-testid="favlist-download-original"
        @click="queueSelected('original')"
      >
        {{ t("legacy.favDlOrig") }}{{ hasSelection ? ` (${selected.length})` : "" }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        type="button"
        data-testid="favlist-archive"
        @click="openArchive"
      >
        {{ t("legacy.favDlArchive") }}{{ hasSelection ? ` (${selected.length})` : "" }}
      </Button>
      <Button variant="outlined" size="compact" type="button" data-testid="favlist-move" @click="openMove">
        {{ t("legacy.favMove") }}{{ hasSelection ? ` (${selected.length})` : "" }}
      </Button>
      <Button variant="text" size="compact" type="button" data-testid="favlist-remove" @click="openRemove">
        {{ t("legacy.favRemove") }}{{ hasSelection ? ` (${selected.length})` : "" }}
      </Button>
    </div>

    <ErrorState
      v-if="error && !items.length"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('common.retry')"
      @retry="loadInitial"
    />

    <div v-else-if="loading" class="favlist__grid" aria-hidden="true">
      <Skeleton v-for="index in 12" :key="index" variant="card" />
    </div>

    <EmptyState
      v-else-if="!items.length"
      :title="t('legacy.noGalleries')"
      :body="t('favorites.list.empty')"
      testid="favlist-empty"
    />

    <div v-else class="favlist__grid" data-testid="favlist-grid">
      <article
        v-for="item in items"
        :key="item.gid"
        class="fav-card"
        :data-gid="item.gid"
        :class="{ 'fav-card--selected': isSelected(item.gid) }"
      >
        <label class="fav-card__check" :title="t('favorites.list.selectItem', { title: item.title || item.gid })">
          <input
            type="checkbox"
            :checked="isSelected(item.gid)"
            :aria-label="t('favorites.list.selectItem', { title: item.title || item.gid })"
            @change="onSelect(item.gid, $event)"
          />
        </label>

        <RouterLink
          v-if="item.gallery_id"
          class="fav-card__link"
          :to="`/gallery/${item.gallery_id}?from=${favcat}`"
        >
          <div class="fav-card__cover">
            <img
              v-if="item.cover_url"
              :src="item.cover_url"
              alt=""
              loading="lazy"
              aria-hidden="true"
            />
            <span v-else class="fav-card__no-cover">{{ t("favorites.list.noCover") }}</span>
            <span class="fav-card__state fav-card__state--local">
              {{ t("legacy.favLocal") }}
            </span>
            <span v-if="item.category" class="fav-card__category">
              {{ categoryLabel(item.category) }}
            </span>
            <span v-if="item.page_count" class="fav-card__pages">{{ item.page_count }} P</span>
          </div>
          <div class="fav-card__body">
            <h2 class="fav-card__title">{{ item.title || `gid ${item.gid}` }}</h2>
            <p v-if="item.note" class="fav-card__note">{{ item.note }}</p>
            <p class="fav-card__meta">
              <span v-if="item.file_size">{{ formatBytes(item.file_size) }}</span>
            </p>
          </div>
        </RouterLink>

        <a
          v-else
          class="fav-card__link"
          :href="externalUrl(item)"
          target="_blank"
          rel="noopener noreferrer"
          :title="t('favorites.list.openEh')"
        >
          <div class="fav-card__cover">
            <img
              v-if="item.cover_url"
              :src="item.cover_url"
              alt=""
              loading="lazy"
              aria-hidden="true"
            />
            <span v-else class="fav-card__no-cover">{{ t("favorites.list.noCover") }}</span>
            <span class="fav-card__state fav-card__state--cloud">
              {{ t("legacy.favCloud") }}
            </span>
            <span v-if="item.category" class="fav-card__category">
              {{ categoryLabel(item.category) }}
            </span>
            <span v-if="item.page_count" class="fav-card__pages">{{ item.page_count }} P</span>
          </div>
          <div class="fav-card__body">
            <h2 class="fav-card__title">{{ item.title || `gid ${item.gid}` }}</h2>
            <p v-if="item.note" class="fav-card__note">{{ item.note }}</p>
            <p class="fav-card__meta">
              <span v-if="item.file_size">{{ formatBytes(item.file_size) }}</span>
            </p>
          </div>
        </a>

        <div v-if="item.tags.length" class="fav-card__tags">
          <button
            v-for="tag in item.tags.slice(0, 6)"
            :key="tagKey(tag)"
            type="button"
            class="fav-card__tag"
            :title="tagKey(tag)"
            @click="applyTag(tag)"
          >
            {{ tagLabel(tag) }}
          </button>
        </div>
      </article>
    </div>

    <div ref="sentinel" class="favlist__sentinel" aria-hidden="true" />

    <div v-if="items.length" class="favlist__footer">
      <Button
        v-if="!allLoaded"
        variant="outlined"
        :loading="loadingMore"
        data-testid="favlist-load-more"
        @click="loadMore"
      >
        {{ t("favorites.list.loadMore") }}
      </Button>
      <span v-else class="favlist__all-loaded">{{ t("favorites.list.allLoaded") }}</span>

      <nav class="favlist__pager" :aria-label="t('legacy.pageNav')">
        <RouterLink
          v-if="filters.page > 1"
          class="favlist__page"
          :to="{ name: 'favorites-list', params: { id: favcat }, query: queryForPage(filters.page - 1) }"
        >
          ‹
        </RouterLink>
        <RouterLink
          v-for="page in pageLinks"
          :key="page"
          class="favlist__page"
          :class="{ 'favlist__page--current': page === filters.page }"
          :aria-current="page === filters.page ? 'page' : undefined"
          :to="{ name: 'favorites-list', params: { id: favcat }, query: queryForPage(page) }"
        >
          {{ page }}
        </RouterLink>
        <RouterLink
          v-if="filters.page < pageCount"
          class="favlist__page"
          :to="{ name: 'favorites-list', params: { id: favcat }, query: queryForPage(filters.page + 1) }"
        >
          ›
        </RouterLink>
      </nav>

      <Select
        class="favlist__page-size"
        :model-value="String(filters.page_size)"
        :options="pageSizeOptions"
        :label="t('legacy.perPage')"
        data-testid="favlist-page-size"
        @update:model-value="onPageSize"
      />
    </div>

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
        <Button :loading="busy" data-testid="favlist-remove-confirm" @click="confirmRemove">
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

.favlist__back {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-3);
}

.favlist__back-link {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.favlist__back-link:hover {
  text-decoration: underline;
}

.favlist__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favlist__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.favlist__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.favlist__cat {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
  vertical-align: middle;
}

.favlist__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.favlist__search {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.favlist__search-input {
  flex: 1 1 280px;
}

.favlist__select {
  min-width: 168px;
}

.favlist__advanced-head {
  display: flex;
  justify-content: flex-start;
}

.favlist__advanced-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-height: 40px;
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.favlist__advanced-count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.favlist__advanced {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--gv-space-3);
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.favlist__range {
  display: flex;
  gap: var(--gv-space-2);
}

.favlist__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.favlist__tag {
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

.favlist__tag-remove {
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.favlist__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.favlist__states {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
}

.favlist__state {
  min-height: 32px;
  padding: 0 var(--gv-space-3);
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.favlist__state--active {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.favlist__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}

.fav-card {
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
  transition: box-shadow var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.fav-card:hover {
  box-shadow: var(--gv-elev-2);
}

.fav-card--selected {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

.fav-card__check {
  position: absolute;
  top: var(--gv-space-2);
  left: var(--gv-space-2);
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, var(--gv-color-surface) 78%, transparent);
  cursor: pointer;
}

.fav-card__check input {
  width: 20px;
  height: 20px;
  accent-color: var(--gv-color-primary);
  cursor: pointer;
}

.fav-card__link {
  display: flex;
  flex-direction: column;
  color: inherit;
  text-decoration: none;
}

.fav-card__cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface-variant);
}

.fav-card__cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.fav-card__no-cover {
  font: var(--gv-type-label-small);
}

.fav-card__state,
.fav-card__category,
.fav-card__pages {
  position: absolute;
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  font: var(--gv-type-label-small);
}

.fav-card__state {
  top: var(--gv-space-2);
  right: var(--gv-space-2);
}

.fav-card__state--local {
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.fav-card__state--cloud {
  background: var(--gv-color-tertiary-container);
  color: var(--gv-color-on-tertiary-container);
}

.fav-card__category {
  left: var(--gv-space-2);
  bottom: var(--gv-space-2);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.fav-card__pages {
  right: var(--gv-space-2);
  bottom: var(--gv-space-2);
  background: color-mix(in srgb, var(--gv-color-surface) 78%, transparent);
  color: var(--gv-color-on-surface);
}

.fav-card__body {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2) var(--gv-space-3) var(--gv-space-1);
}

.fav-card__title {
  display: -webkit-box;
  min-height: calc(var(--gv-type-title-small-line) * 2);
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.fav-card__note,
.fav-card__meta {
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fav-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  padding: 0 var(--gv-space-3) var(--gv-space-2);
}

.fav-card__tag {
  max-width: 100%;
  overflow: hidden;
  padding: 0 var(--gv-space-1);
  border: 0;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.fav-card__tag:hover {
  background: var(--gv-color-surface-container-highest);
}

.favlist__sentinel {
  height: var(--gv-space-1);
}

.favlist__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3) 0;
}

.favlist__all-loaded {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.favlist__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.favlist__page {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.favlist__page:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.favlist__page--current {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.favlist__page-size {
  min-width: 120px;
}

@media (max-width: 599px) {
  .favlist__grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }

  .favlist__advanced {
    grid-template-columns: 1fr;
  }

  .favlist__range {
    flex-direction: column;
  }
}
</style>
