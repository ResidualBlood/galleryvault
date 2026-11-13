<script setup lang="ts">
/**
 * Home / browse page (DESIGN.md C19).
 *
 * PageHeader → Toolbar (search, search action, random, view toggle) → continue
 * reading strips → recently added collection (grid / list / table, remembered
 * per page) → tag overview. The tag overview sits *after* the main list so the
 * first cards are visible in a 1280x900 viewport (audit BR-04).
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { onBeforeRouteLeave, RouterLink, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import {
  BROWSE_TABLE_COLUMNS,
  orderByFor,
  type SortState,
  type TableColumn,
} from "@/components/gallery/table-columns";
import TagSuggest from "@/views/library/TagSuggest.vue";
import OnlineContinue from "@/views/history/online/OnlineContinue.vue";
import BrowseTagOverview from "./extra/BrowseTagOverview.vue";
import { ensureLibraryMessages } from "@/views/library/messages";
import { useViewMode } from "@/composables/useViewMode";
import {
  fetchHistory,
  fetchRandomGallery,
  galleryThumbUrl,
  type HistoryItem,
  type TagSuggestion,
} from "@/api/library";
import { progressPercent, useLibraryStore } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";

ensureLibraryMessages();

const { t } = useI18n();
const router = useRouter();
const store = useLibraryStore();
const settings = useSettingsStore();
const ui = useUiStore();

const view = useViewMode("browse", {
  allowed: ["grid", "list", "table"] as const,
  fallback: "grid",
});

const term = ref("");
const history = ref<HistoryItem[]>([]);
const historyLoading = ref(true);
const randomBusy = ref(false);
const sort = ref<SortState | null>(null);
let historyController: AbortController | null = null;

const latestTotal = computed(() => store.total);

function queryFor(orderBy: string | null) {
  return {
    page_size: settings.pageSize,
    tags_limit: 0,
    ...(orderBy ? { order_by: orderBy } : {}),
  };
}

async function loadHistory(): Promise<void> {
  historyController?.abort();
  historyController = new AbortController();
  historyLoading.value = true;
  try {
    const data = await fetchHistory(1, 8, historyController.signal);
    history.value = data.items ?? [];
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") return;
    history.value = [];
  } finally {
    historyLoading.value = false;
  }
}

function onSearch(): void {
  const q = term.value.trim();
  void router.push({ name: "library", query: q ? { q } : {} });
}

function onSelectTag(tag: TagSuggestion): void {
  const key = tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name;
  void router.push({ name: "library", query: { tags: key } });
}

async function openRandom(): Promise<void> {
  if (randomBusy.value) return;
  randomBusy.value = true;
  try {
    const data = await fetchRandomGallery();
    await router.push({ name: "gallery", params: { id: data.id } });
  } catch {
    ui.error(t("library.home.randomFailed"));
  } finally {
    randomBusy.value = false;
  }
}

function onSort(column: TableColumn, direction: "asc" | "desc"): void {
  const mapped = orderByFor(column, direction);
  if (!mapped) return;
  sort.value = { key: column.key, direction };
  store.start(queryFor(mapped));
}

function historyTitle(item: HistoryItem): string {
  return item.display_title || item.title || `#${item.gallery_id}`;
}

function historyProgress(item: HistoryItem): number {
  return progressPercent(item.current_page, item.total_pages);
}

function thumbFor(item: HistoryItem): string {
  return galleryThumbUrl(item.gallery_id);
}

function hideBroken(event: Event): void {
  (event.target as HTMLImageElement).style.display = "none";
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

onMounted(() => {
  store.start(queryFor(null), settings.pageSize);
  restoreScrollSoon();
  void loadHistory();
});

onBeforeRouteLeave(() => {
  store.saveScroll(window.scrollY);
});

onBeforeUnmount(() => {
  historyController?.abort();
  store.saveScroll(window.scrollY);
});
</script>

<template>
  <section class="browse" data-testid="browse-view">
    <PageHeader :title="t('library.home.title')" testid="browse-header" />

    <form class="browse__search-form" role="search" @submit.prevent="onSearch">
      <Toolbar testid="browse-toolbar">
        <TagSuggest
          v-model="term"
          class="browse__search"
          :label="t('library.page.search')"
          :placeholder="t('library.page.searchPlaceholder')"
          @select="onSelectTag"
        />
        <ToolbarGroup end>
          <Button type="submit" icon="search">{{ t("legacy.search") }}</Button>
          <Button
            type="button"
            variant="tonal"
            icon="random"
            :loading="randomBusy"
            data-testid="random-button"
            @click="openRandom"
          >
            {{ t("library.home.random") }}
          </Button>
          <ViewModeToggle
            :model-value="view.mode.value"
            :options="view.available.value"
            @update:model-value="view.setMode"
          />
        </ToolbarGroup>
      </Toolbar>
    </form>

    <section v-if="history.length || historyLoading" class="browse__section" data-testid="continue-reading">
      <div class="browse__section-head">
        <h2 class="browse__section-title">{{ t("library.continueReading.title") }}</h2>
        <RouterLink class="browse__link" to="/history">
          {{ t("library.continueReading.viewAll") }}
        </RouterLink>
      </div>

      <div v-if="historyLoading" class="browse__continue">
        <Skeleton v-for="index in 4" :key="index" variant="card" />
      </div>
      <div v-else class="browse__continue">
        <article
          v-for="item in history"
          :key="item.gallery_id"
          class="continue-card"
          :data-testid="`continue-${item.gallery_id}`"
        >
          <RouterLink
            class="continue-card__cover"
            :to="{ name: 'reader', params: { id: item.gallery_id, page: item.current_page } }"
          >
            <img
              class="continue-card__image"
              :src="thumbFor(item)"
              :alt="historyTitle(item)"
              loading="lazy"
              decoding="async"
              @error="hideBroken"
            />
            <span class="continue-card__progress">
              <span
                class="continue-card__progress-fill"
                :style="{ width: `${historyProgress(item)}%` }"
              />
            </span>
          </RouterLink>
          <RouterLink
            class="continue-card__title"
            :to="{ name: 'gallery', params: { id: item.gallery_id } }"
            :title="historyTitle(item)"
          >
            {{ historyTitle(item) }}
          </RouterLink>
          <div class="continue-card__meta">
            <span>{{ historyProgress(item) }}%</span>
            <RouterLink
              class="continue-card__read"
              :to="{ name: 'reader', params: { id: item.gallery_id, page: item.current_page } }"
            >
              {{ t("library.continueReading.readNow") }}
            </RouterLink>
          </div>
        </article>
      </div>
    </section>

    <OnlineContinue class="browse__section" />

    <section class="browse__section browse__latest">
      <div class="browse__section-head">
        <h2 class="browse__section-title">
          {{ t("library.home.latest") }}
          <span v-if="latestTotal" class="browse__count">{{ latestTotal }}</span>
        </h2>
      </div>

      <div v-if="store.initialLoading" class="browse__skeletons" aria-hidden="true">
        <Skeleton v-for="index in 12" :key="index" variant="card" />
      </div>

      <ErrorState
        v-else-if="store.error && store.items.length === 0"
        :title="t('common.errorTitle')"
        :body="store.error"
        :retry-label="t('common.retry')"
        @retry="store.retry"
      />

      <div v-else-if="!store.items.length" class="browse__empty">
        <!-- C18: an empty table keeps its header (only the table view). -->
        <GalleryCollection
          v-if="view.mode.value === 'table'"
          :items="[]"
          mode="table"
          :columns="BROWSE_TABLE_COLUMNS"
          :sort="sort"
          testid="browse-grid"
          @sort="onSort"
        />
        <EmptyState
          :title="t('library.page.emptyTitle')"
          :body="t('legacy.noGalleries')"
          testid="browse-empty"
        />
      </div>

      <GalleryCollection
        v-else
        :items="store.items"
        :mode="view.mode.value"
        :columns="BROWSE_TABLE_COLUMNS"
        :sort="sort"
        :loading="store.loading"
        :has-more="store.hasMore"
        :error="store.error"
        :failures="store.failures"
        :total="store.total"
        testid="browse-grid"
        @load-more="store.loadMore"
        @retry="store.retry"
        @sort="onSort"
      />
    </section>

    <BrowseTagOverview class="browse__section" />
  </section>
</template>

<style scoped>
.browse {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

/* C17: the toolbar sticks under the 56px app topbar; the table header uses
   `--gv-table-head-top` so it parks below the toolbar instead of behind it. */
.browse {
  --gv-table-head-top: calc(
    var(--gv-size-topbar) + var(--gv-size-control-lg) + var(--gv-space-4)
  );
}

.browse__search-form {
  position: sticky;
  top: var(--gv-size-topbar);
  z-index: 7;
  display: block;
  width: 100%;
  padding-block: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface);
}

.browse__search :deep(.tag-suggest__input) {
  height: var(--gv-size-control-lg);
  font: var(--gv-type-body-medium);
}

.browse__section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.browse__section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.browse__section-title {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.browse__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.browse__link {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.browse__link:hover {
  text-decoration: underline;
}

/* BR-10: fade the right edge of the horizontal strip instead of a hard cut. */
.browse__continue {
  display: grid;
  grid-auto-columns: 160px;
  grid-auto-flow: column;
  gap: var(--gv-space-3);
  padding-bottom: var(--gv-space-1);
  overflow-x: auto;
  overscroll-behavior-x: contain;
  mask-image: linear-gradient(to right, black calc(100% - var(--gv-space-6)), transparent);
}

.continue-card {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 160px;
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.continue-card__cover {
  position: relative;
  display: block;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  overflow: hidden;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
}

.continue-card__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.continue-card__progress {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: var(--gv-space-1);
  background: var(--gv-color-outline-variant);
}

.continue-card__progress-fill {
  display: block;
  height: 100%;
  background: var(--gv-color-primary);
}

.continue-card__title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
}

.continue-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.continue-card__read {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.browse__empty {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.browse__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: var(--gv-space-3);
}

@media (min-width: 840px) {
  .browse {
    gap: var(--gv-space-6);
  }

  .browse__continue {
    grid-auto-columns: 180px;
  }
}
</style>
