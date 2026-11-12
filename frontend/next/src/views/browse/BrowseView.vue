<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { onBeforeRouteLeave, RouterLink, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import VirtualGrid from "@/components/gallery/VirtualGrid.vue";
import TagSuggest from "@/views/library/TagSuggest.vue";
import OnlineContinue from "@/views/history/online/OnlineContinue.vue";
import { ensureLibraryMessages } from "@/views/library/messages";
import { fetchHistory, fetchRandomGallery, galleryThumbUrl, type HistoryItem, type TagSuggestion } from "@/api/library";
import { progressPercent, useLibraryStore } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";

ensureLibraryMessages();

const { t } = useI18n();
const router = useRouter();
const store = useLibraryStore();
const settings = useSettingsStore();
const ui = useUiStore();

const term = ref("");
const history = ref<HistoryItem[]>([]);
const historyLoading = ref(true);
const randomBusy = ref(false);
let historyController: AbortController | null = null;

const latestTotal = computed(() => store.total);

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
  store.start({ page_size: settings.pageSize }, settings.pageSize);
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
    <header class="browse__header">
      <p class="browse__eyebrow">{{ t("library.home.eyebrow") }}</p>
      <h1 class="browse__title">{{ t("library.home.title") }}</h1>
    </header>

    <form class="browse__toolbar" role="search" @submit.prevent="onSearch">
      <TagSuggest
        v-model="term"
        :label="t('library.page.search')"
        :placeholder="t('library.page.searchPlaceholder')"
        @select="onSelectTag"
      />
      <Button type="submit" variant="filled">{{ t("legacy.search") }}</Button>
      <Button
        type="button"
        variant="tonal"
        :loading="randomBusy"
        data-testid="random-button"
        @click="openRandom"
      >
        ⚄ {{ t("library.home.random") }}
      </Button>
    </form>

    <section v-if="history.length || historyLoading" class="browse__section" data-testid="continue-reading">
      <div class="browse__section-head">
        <h2 class="browse__section-title">{{ t("library.continueReading.title") }}</h2>
        <RouterLink class="browse__link" to="/history">
          {{ t("library.continueReading.viewAll") }} →
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

    <section class="browse__section">
      <div class="browse__section-head">
        <h2 class="browse__section-title">
          {{ t("library.home.latest") }}
          <span class="browse__count">{{ latestTotal }}</span>
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

      <EmptyState
        v-else-if="!store.items.length"
        :title="t('library.page.emptyTitle')"
        :body="t('legacy.noGalleries')"
        testid="browse-empty"
      />

      <VirtualGrid
        v-else
        :items="store.items"
        :loading="store.loading"
        :has-more="store.hasMore"
        :error="store.error"
        :failures="store.failures"
        :total="store.total"
        testid="browse-grid"
        @load-more="store.loadMore"
        @retry="store.retry"
      />
    </section>
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

.browse__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.browse__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.browse__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.browse__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
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

.browse__continue {
  display: grid;
  grid-auto-columns: 160px;
  grid-auto-flow: column;
  gap: var(--gv-space-3);
  padding-bottom: var(--gv-space-1);
  overflow-x: auto;
  overscroll-behavior-x: contain;
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
