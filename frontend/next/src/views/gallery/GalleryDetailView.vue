<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ApiError } from "@/api/client";
import {
  galleryThumbUrl,
  getGallery,
  getGalleryProgress,
  type GalleryDetail,
  type GalleryProgress,
  type GalleryTag,
} from "@/api/gallery";
import Button from "@/components/ui/Button.vue";
import GalleryDetailLayout from "@/components/gallery/GalleryDetailLayout.vue";
import TagGroups from "@/components/gallery/TagGroups.vue";
import ThumbGrid from "@/components/gallery/ThumbGrid.vue";
import { useViewRequest } from "@/composables/useViewRequest";
import { useUiStore } from "@/stores/ui";
import {
  categoryKey,
  formatBytes,
  formatDate,
  formatRating,
  parseGalleryId,
} from "./format";
import "./i18n";

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const request = useViewRequest();
const { t, te, locale } = useI18n();

const gallery = ref<GalleryDetail | null>(null);
const progress = ref<GalleryProgress | null>(null);
const loading = ref(true);
const error = ref(false);
const coverFailed = ref(false);

const status = computed<"loading" | "ready" | "error">(() => {
  if (loading.value) return "loading";
  if (error.value) return "error";
  return "ready";
});

const pageCount = computed(() => {
  if (!gallery.value) return 0;
  return gallery.value.page_count || gallery.value.pages?.length || 0;
});

const coverUrl = computed(() =>
  gallery.value && pageCount.value > 0 ? galleryThumbUrl(gallery.value.id, 0) : "",
);

const subtitle = computed(() => {
  const item = gallery.value;
  if (!item) return "";
  const candidates = [item.title_jpn, item.title_english];
  for (const candidate of candidates) {
    if (candidate && candidate !== item.title) return candidate;
  }
  return "";
});

const category = computed(() => categoryKey(gallery.value?.category));

const categoryStyle = computed<Record<string, string>>(() => ({
  "--category-bg": `var(--gv-cat-${category.value})`,
  "--category-ink": `var(--gv-cat-${category.value}-ink)`,
}));

function categoryLabel(): string {
  const key = `gallery.categories.${category.value}`;
  return te(key) ? t(key) : category.value;
}

const hasProgress = computed(() => {
  const page = progress.value?.current_page ?? 0;
  return page > 0 && page < pageCount.value;
});

const continuePage = computed(() => {
  if (!hasProgress.value) return 0;
  return Math.min(progress.value?.current_page ?? 0, Math.max(0, pageCount.value - 1));
});

const postedLabel = computed(() =>
  formatDate(gallery.value?.posted_at, locale.value === "zh" ? "zh-CN" : "en-US"),
);

const sizeLabel = computed(() =>
  formatBytes(gallery.value?.file_size ?? gallery.value?.storage_size),
);

const ratingLabel = computed(() =>
  formatRating(gallery.value?.rating ?? gallery.value?.local_rating),
);

const qualityLabel = computed(() => {
  const quality = gallery.value?.image_quality;
  if (quality === "original" || quality === "resample") {
    return t(`gallery.quality.${quality}`);
  }
  return "";
});

function fallbackProgress(detail: GalleryDetail): GalleryProgress {
  return {
    gallery_id: detail.id,
    current_page:
      typeof detail.reading_progress === "number" ? detail.reading_progress : 0,
    total_pages: detail.page_count,
    updated_at: null,
  };
}

function openPage(index: number): void {
  const item = gallery.value;
  if (!item) return;
  void router.push({ name: "reader", params: { id: item.id, page: index } });
}

function continueReading(): void {
  openPage(continuePage.value);
}

function readFromStart(): void {
  openPage(0);
}

function selectTag(tag: GalleryTag): void {
  void router.push({
    name: "library",
    query: { tags: `${tag.namespace}:${tag.name}`, tag_mode: "and" },
  });
}

function invalid(): void {
  ui.error(t("gallery.invalidId"));
  void router.replace({ name: "browse" });
}

async function load(): Promise<void> {
  const raw = route.params.id;
  const id = parseGalleryId(Array.isArray(raw) ? raw[0] : raw);
  if (id === null) {
    invalid();
    return;
  }

  const context = request.begin("gallery", String(id));
  loading.value = true;
  error.value = false;
  coverFailed.value = false;
  try {
    const [detailResult, progressResult] = await Promise.allSettled([
      getGallery(id, { signal: context.signal }),
      getGalleryProgress(id, { signal: context.signal }),
    ]);
    if (context.stale("gallery", String(id))) return;

    if (detailResult.status === "rejected") throw detailResult.reason;
    gallery.value = detailResult.value;
    progress.value =
      progressResult.status === "fulfilled"
        ? progressResult.value
        : fallbackProgress(detailResult.value);
  } catch (cause) {
    if (context.stale()) return;
    if (cause instanceof DOMException && cause.name === "AbortError") return;
    if (cause instanceof ApiError && (cause.status === 404 || cause.status === 422)) {
      invalid();
      return;
    }
    error.value = true;
  } finally {
    if (!context.stale()) loading.value = false;
  }
}

watch(
  () => route.params.id,
  () => {
    void load();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  request.abort();
});
</script>

<template>
  <GalleryDetailLayout
    :status="status"
    :error-title="t('gallery.loadFailed')"
    @retry="load"
  >
    <template #header>
      <article v-if="gallery" class="gallery-header">
        <div class="gallery-header__cover">
          <img
            v-if="coverUrl && !coverFailed"
            class="gallery-header__image"
            data-testid="gallery-cover"
            :src="coverUrl"
            :alt="t('gallery.coverAlt', { title: gallery.title })"
            @error="coverFailed = true"
          />
          <div v-else class="gallery-header__fallback" data-testid="gallery-cover-fallback">
            <span>{{ t("gallery.coverMissing") }}</span>
          </div>
        </div>

        <div class="gallery-header__info">
          <span class="gallery-header__category" :style="categoryStyle">
            {{ categoryLabel() }}
          </span>
          <h1 class="gallery-header__title" data-testid="gallery-title">
            {{ gallery.title }}
          </h1>
          <p v-if="subtitle" class="gallery-header__subtitle" data-testid="gallery-subtitle">
            {{ subtitle }}
          </p>

          <dl class="gallery-header__meta">
            <div class="gallery-header__meta-item">
              <dt>{{ t("gallery.meta.uploader") }}</dt>
              <dd>{{ gallery.uploader || t("gallery.unknown") }}</dd>
            </div>
            <div class="gallery-header__meta-item">
              <dt>{{ t("gallery.meta.posted") }}</dt>
              <dd>{{ postedLabel || t("gallery.unknown") }}</dd>
            </div>
            <div class="gallery-header__meta-item">
              <dt>{{ t("gallery.meta.pages") }}</dt>
              <dd>{{ pageCount }}</dd>
            </div>
            <div class="gallery-header__meta-item">
              <dt>{{ t("gallery.meta.size") }}</dt>
              <dd>{{ sizeLabel || t("gallery.unknown") }}</dd>
            </div>
            <div class="gallery-header__meta-item">
              <dt>{{ t("gallery.meta.rating") }}</dt>
              <dd>{{ ratingLabel || t("gallery.unknown") }}</dd>
            </div>
            <div v-if="qualityLabel" class="gallery-header__meta-item">
              <dt>{{ t("gallery.meta.quality") }}</dt>
              <dd>{{ qualityLabel }}</dd>
            </div>
          </dl>
        </div>
      </article>
    </template>

    <template #actions>
      <div v-if="gallery" class="gallery-actions">
        <Button data-testid="continue-reading" variant="filled" @click="continueReading">
          {{ hasProgress ? t("gallery.continueReading") : t("gallery.read") }}
        </Button>
        <Button
          v-if="hasProgress"
          data-testid="read-from-start"
          variant="outlined"
          @click="readFromStart"
        >
          {{ t("gallery.restart") }}
        </Button>
      </div>
    </template>

    <template #tags>
      <div v-if="gallery" class="gallery-section">
        <div class="gallery-section__head">
          <h2 class="gallery-section__title">{{ t("gallery.tags") }}</h2>
        </div>
        <TagGroups :tags="gallery.tags ?? []" @select="selectTag" />
      </div>
    </template>

    <template #thumbs>
      <div v-if="gallery" class="gallery-section">
        <div class="gallery-section__head">
          <h2 class="gallery-section__title">{{ t("gallery.thumbs") }}</h2>
          <span class="gallery-section__count">
            {{ t("gallery.thumbsCount", { count: pageCount }) }}
          </span>
        </div>
        <ThumbGrid
          :gallery-id="gallery.id"
          :pages="gallery.pages ?? []"
          :current-page="progress?.current_page ?? -1"
          @select="openPage"
        />
      </div>
    </template>
  </GalleryDetailLayout>
</template>

<style scoped>
.gallery-header {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--gv-space-4);
}

.gallery-header__cover {
  width: min(180px, 45vw);
}

.gallery-header__image,
.gallery-header__fallback {
  display: block;
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-highest);
}

.gallery-header__image {
  object-fit: cover;
}

.gallery-header__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-align: center;
}

.gallery-header__info {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.gallery-header__category {
  align-self: flex-start;
  height: 24px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--category-bg, var(--gv-cat-misc));
  color: var(--category-ink, var(--gv-cat-misc-ink));
  font: var(--gv-type-label-small);
  line-height: 24px;
}

.gallery-header__title {
  margin: 0;
  font: var(--gv-type-headline-small);
  color: var(--gv-color-on-surface);
  overflow-wrap: anywhere;
}

.gallery-header__subtitle {
  margin: 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
  overflow-wrap: anywhere;
}

.gallery-header__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--gv-space-2) var(--gv-space-4);
  margin: var(--gv-space-2) 0 0;
}

.gallery-header__meta-item {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.gallery-header__meta-item dt {
  font: var(--gv-type-label-medium);
  color: var(--gv-color-on-surface-variant);
}

.gallery-header__meta-item dd {
  margin: 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface);
  overflow-wrap: anywhere;
}

.gallery-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.gallery-section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.gallery-section__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--gv-space-2);
}

.gallery-section__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.gallery-section__count {
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

@media (min-width: 840px) {
  .gallery-header {
    grid-template-columns: 176px minmax(0, 1fr);
    align-items: start;
  }

  .gallery-header__cover {
    width: 176px;
  }
}
</style>
