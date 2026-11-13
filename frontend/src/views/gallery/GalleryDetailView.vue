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
import GalleryActions from "@/components/actions/GalleryActions.vue";
import GalleryDetailLayout, {
  type DetailCrumb,
  type DetailMetaItem,
} from "@/components/gallery/GalleryDetailLayout.vue";
import GalleryManageSection from "./extra/GalleryManageSection.vue";
import TagGroups from "@/components/gallery/TagGroups.vue";
import ThumbGrid from "@/components/gallery/ThumbGrid.vue";
import { useTagNavigation } from "@/components/tags/useTagNavigation";
import { useViewRequest } from "@/composables/useViewRequest";
import { useUiStore } from "@/stores/ui";
import {
  categoryKey,
  formatBytes,
  formatPosted,
  formatRating,
  parseGalleryId,
} from "./format";
import "./i18n";

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const request = useViewRequest();
const { t, te, locale } = useI18n();
const tagNavigation = useTagNavigation("local");

const gallery = ref<GalleryDetail | null>(null);
const progress = ref<GalleryProgress | null>(null);
const loading = ref(true);
const error = ref(false);

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

const title = computed(() => gallery.value?.title ?? "");
const titleTestid = "gallery-title";

const subtitle = computed(() => {
  const item = gallery.value;
  if (!item) return "";
  const candidates = [item.title_jpn, item.title_english];
  for (const candidate of candidates) {
    if (candidate && candidate !== item.title) return candidate;
  }
  return "";
});

const crumbs = computed<DetailCrumb[]>(() => [
  { label: t("app.nav.library"), to: "/library" },
]);

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
  formatPosted(gallery.value?.posted_at, locale.value === "zh" ? "zh-CN" : "en-US"),
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

/* GD-05: optional facts (uploader / rating) are dropped instead of repeated as
   "未知" placeholders; only the post date keeps an explicit "未知" (OD-01), so a
   page never shows more than one unknown. The layout degrades to a single
   summary line when fewer than two rows survive. */
const meta = computed<DetailMetaItem[]>(() => {
  const item = gallery.value;
  if (!item) return [];
  const rows: DetailMetaItem[] = [];
  if (item.uploader) rows.push({ label: t("gallery.meta.uploader"), value: item.uploader });
  rows.push({
    label: t("gallery.meta.posted"),
    value: postedLabel.value || t("gallery.unknown"),
  });
  if (pageCount.value > 0) {
    rows.push({ label: t("gallery.meta.pages"), value: String(pageCount.value) });
  }
  if (sizeLabel.value) rows.push({ label: t("gallery.meta.size"), value: sizeLabel.value });
  if (ratingLabel.value) {
    rows.push({ label: t("gallery.meta.rating"), value: ratingLabel.value, icon: "star" });
  }
  if (qualityLabel.value) rows.push({ label: t("gallery.meta.quality"), value: qualityLabel.value });
  return rows;
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
  void tagNavigation.navigate(tag);
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
    :title="title"
    :title-testid="titleTestid"
    subtitle-testid="gallery-subtitle"
    :subtitle="subtitle"
    :crumbs="crumbs"
    back-fallback="/library"
    :cover-url="coverUrl"
    :cover-alt="t('gallery.coverAlt', { title })"
    cover-testid="gallery-cover"
    cover-fallback-testid="gallery-cover-fallback"
    :cover-fallback-label="t('gallery.coverMissing')"
    :meta="meta"
    :error-title="t('gallery.loadFailed')"
    @retry="load"
  >
    <template #badges>
      <span v-if="gallery" class="gallery-detail__category" :style="categoryStyle">
        {{ categoryLabel() }}
      </span>
    </template>

    <template #actions>
      <template v-if="gallery">
        <Button data-testid="continue-reading" variant="filled" @click="continueReading">
          {{ hasProgress ? t("gallery.continueReading") : t("gallery.read") }}
        </Button>
        <Button
          v-if="hasProgress"
          class="gallery-detail__restart"
          data-testid="read-from-start"
          variant="outlined"
          @click="readFromStart"
        >
          {{ t("gallery.restart") }}
        </Button>
        <GalleryActions
          v-if="gallery.gid && gallery.token"
          :gid="gallery.gid"
          :token="gallery.token"
          :title="gallery.title"
          source="local"
          density="detail"
          :show-read="false"
          :favorited="Boolean(gallery.favorite)"
          :favcat="gallery.favorite_category ?? null"
          :in-library="true"
          download-status="success"
        />
      </template>
    </template>

    <template #tags>
      <div v-if="gallery" class="gallery-detail__section">
        <div class="gallery-detail__head">
          <h2 class="gallery-detail__title">{{ t("gallery.tags") }}</h2>
        </div>
        <TagGroups :tags="gallery.tags ?? []" source="local" @select="selectTag" />
      </div>
    </template>

    <template #thumbs>
      <div v-if="gallery" class="gallery-detail__section">
        <div class="gallery-detail__head">
          <h2 class="gallery-detail__title">{{ t("gallery.thumbs") }}</h2>
          <span class="gallery-detail__count">
            {{ t("gallery.thumbsCount", { count: pageCount }) }}
          </span>
        </div>
        <ThumbGrid
          :gallery-id="gallery.id"
          :pages="gallery.pages ?? []"
          :current-page="hasProgress ? (progress?.current_page ?? -1) : -1"
          @select="openPage"
        />
      </div>
    </template>

    <template #extra>
      <GalleryManageSection v-if="gallery" :gallery="gallery" @refresh="load" />
    </template>
  </GalleryDetailLayout>
</template>

<style scoped>
.gallery-detail__category {
  display: inline-flex;
  align-items: center;
  height: var(--gv-size-tag-lg);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--category-bg, var(--gv-cat-misc));
  color: var(--category-ink, var(--gv-cat-misc-ink));
  font: var(--gv-type-label-small);
}

/* --gv-bp-compact = 600px: "restart" is the secondary read entry and yields
   to the primary CTA + the two quick actions on one mobile row (GD-03). */
@media (max-width: 599.98px) {
  .gallery-detail__restart {
    display: none;
  }
}

.gallery-detail__section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  min-width: 0;
}

.gallery-detail__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.gallery-detail__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.gallery-detail__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
