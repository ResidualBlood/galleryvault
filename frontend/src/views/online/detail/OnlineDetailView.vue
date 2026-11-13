<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ApiError } from "@/api/client";
import {
  fetchOnlineDetail,
  mapOnlineState,
  officialGalleryUrl,
  type OnlineGallery,
  type OnlineState,
  type OnlineTag,
} from "@/api/eh";
import Button from "@/components/ui/Button.vue";
import Icon from "@/components/icons/Icon.vue";
import GalleryActions from "@/components/actions/GalleryActions.vue";
import GalleryDetailLayout, {
  type DetailCrumb,
  type DetailMetaItem,
} from "@/components/gallery/GalleryDetailLayout.vue";
import TagGroups from "@/components/gallery/TagGroups.vue";
import { useTagNavigation } from "@/components/tags/useTagNavigation";
import { useViewRequest } from "@/composables/useViewRequest";
import { useFavoritesStore } from "@/stores/favorites";
import { useDownloadsStore } from "@/stores/downloads";
import { useUiStore } from "@/stores/ui";
import { categoryToken } from "@/views/online/list/category";
import OnlineStateNotice from "@/views/online/list/OnlineStateNotice.vue";
import { ensureOnlineMessages } from "@/views/online/list/messages";
import { formatBytes } from "@/stores/library";
import { formatPosted } from "@/views/gallery/format";
import OnlineThumbGrid from "./OnlineThumbGrid.vue";
import "@/views/gallery/i18n";

ensureOnlineMessages();

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const favorites = useFavoritesStore();
const downloads = useDownloadsStore();
const request = useViewRequest();
const { t, te, locale } = useI18n();
const tagNavigation = useTagNavigation("online");

const gallery = ref<OnlineGallery | null>(null);
const state = ref<OnlineState>("ok");
const loading = ref(true);
const error = ref(false);

const status = computed<"loading" | "ready" | "error">(() => {
  if (loading.value) return "loading";
  if (error.value) return "error";
  return "ready";
});

const showState = computed(
  () => !loading.value && !error.value && state.value !== "ok",
);

const title = computed(() => gallery.value?.title ?? "");

const subtitle = computed(() => {
  const item = gallery.value;
  if (!item || !item.title_jpn || item.title_jpn === item.title) return "";
  return item.title_jpn;
});

const crumbs = computed<DetailCrumb[]>(() => [
  { label: t("app.nav.online"), to: "/online" },
]);

const coverUrl = computed(() => {
  const url = gallery.value?.thumb?.trim() ?? "";
  return /^https?:\/\//i.test(url) ? url : "";
});

const posted = computed(() =>
  formatPosted(gallery.value?.posted, locale.value === "zh" ? "zh-CN" : "en-US"),
);
const size = computed(() => formatBytes(gallery.value?.file_size));
const rating = computed(() => {
  const value = gallery.value?.rating;
  return typeof value === "number" && value > 0 ? value.toFixed(1) : "";
});

const category = computed(() => gallery.value?.category ?? "misc");
const categoryLabel = computed(() => {
  const key = `online.categories.${category.value}`;
  return te(key) ? t(key) : t("online.categories.misc");
});
const categoryStyle = computed<Record<string, string>>(() => ({
  "--category-bg": `var(${categoryToken(category.value)})`,
  "--category-ink": `var(${categoryToken(category.value)}-ink)`,
}));

const officialUrl = computed(() =>
  gallery.value ? officialGalleryUrl(gallery.value.gid, gallery.value.token) : "",
);

/* Quick-action stores win over the load-time snapshot so a favourite / download
   started here keeps the header, badges and reader consistent. */
const favoriteEntry = computed(() => favorites.entries[gallery.value?.gid ?? 0]);
const favorited = computed(
  () => favoriteEntry.value?.favorited ?? Boolean(gallery.value?.favorited),
);
const favcat = computed(
  () => favoriteEntry.value?.favcat ?? gallery.value?.favcat ?? null,
);
const inLibrary = computed(
  () => downloads.entries[gallery.value?.gid ?? 0]?.inLibrary ?? Boolean(gallery.value?.in_library),
);

/* OD-01 / OD-02: unknown fields are dropped (no "未知" filler) and the rating
   carries the star glyph; the layout keeps the grid from orphaning a cell. */
const meta = computed<DetailMetaItem[]>(() => {
  const item = gallery.value;
  if (!item) return [];
  const rows: DetailMetaItem[] = [];
  if (item.uploader) rows.push({ label: t("online.detail.uploader"), value: item.uploader });
  rows.push({
    label: t("online.detail.posted"),
    value: posted.value || t("online.detail.unknown"),
  });
  if (item.pages > 0) {
    rows.push({ label: t("online.detail.pages"), value: String(item.pages) });
  }
  if (size.value) rows.push({ label: t("online.detail.size"), value: size.value });
  if (rating.value) {
    rows.push({ label: t("online.detail.rating"), value: rating.value, icon: "star" });
  }
  return rows;
});

function read(): void {
  const item = gallery.value;
  if (!item) return;
  void router.push({
    name: "online-reader",
    params: { gid: item.gid, token: item.token, page: 0 },
  });
}

function openPage(page: number): void {
  const item = gallery.value;
  if (!item) return;
  void router.push({
    name: "online-reader",
    params: { gid: item.gid, token: item.token, page },
  });
}

function selectTag(tag: OnlineTag): void {
  void tagNavigation.navigate(tag);
}

function parseParams(): { gid: number; token: string } | null {
  const rawGid = Array.isArray(route.params.gid) ? route.params.gid[0] : route.params.gid;
  const rawToken = Array.isArray(route.params.token)
    ? route.params.token[0]
    : route.params.token;
  const gid = Number.parseInt(String(rawGid ?? ""), 10);
  const token = String(rawToken ?? "").trim();
  if (!Number.isInteger(gid) || gid <= 0 || !/^[0-9a-z]+$/i.test(token)) return null;
  return { gid, token };
}

function invalid(): void {
  ui.error(t("online.detail.invalid"));
  void router.replace({ name: "online" });
}

async function load(): Promise<void> {
  const params = parseParams();
  if (!params) {
    invalid();
    return;
  }
  const context = request.begin("online-detail", `${params.gid}/${params.token}`);
  loading.value = true;
  error.value = false;
  try {
    const data = await fetchOnlineDetail(params.gid, params.token, context.signal);
    if (context.stale()) return;
    const mapped = mapOnlineState(data.state);
    if (mapped !== "ok") {
      state.value = mapped;
      gallery.value = null;
      return;
    }
    if (!data.gallery) {
      state.value = "error";
      gallery.value = null;
      return;
    }
    state.value = "ok";
    gallery.value = data.gallery;
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
  () => [route.params.gid, route.params.token] as const,
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
  <section class="online-detail" data-testid="online-detail-view">
    <OnlineStateNotice v-if="showState" :state="state" @retry="load" />

    <GalleryDetailLayout
      v-else
      :status="status"
      :title="title"
      title-testid="online-title"
      subtitle-testid="online-subtitle"
      :subtitle="subtitle"
      :crumbs="crumbs"
      back-fallback="/online"
      :cover-url="coverUrl"
      :cover-alt="t('online.detail.coverAlt', { title })"
      cover-testid="online-cover"
      cover-fallback-testid="online-cover-fallback"
      :cover-fallback-label="t('online.detail.coverMissing')"
      cover-no-referrer
      :meta="meta"
      :error-title="t('online.detail.loadFailed')"
      @retry="load"
    >
      <template #badges>
        <template v-if="gallery">
          <span class="online-detail__category" :style="categoryStyle">
            {{ categoryLabel }}
          </span>
          <span v-if="inLibrary" class="online-detail__status" data-testid="online-in-library">
            {{ t("online.detail.inLibrary") }}
          </span>
          <RouterLink
            v-if="gallery.newer"
            class="online-detail__newer"
            :to="{
              name: 'online-detail',
              params: { gid: gallery.newer.gid, token: gallery.newer.token },
            }"
            data-testid="online-newer"
          >
            {{ t("online.detail.newer") }}
            <Icon name="chevron-right" size="dense" />
          </RouterLink>
        </template>
      </template>

      <template #actions>
        <div v-if="gallery" class="online-actions" data-testid="online-actions">
          <Button variant="filled" data-testid="online-read" @click="read">
            {{ t("online.detail.read") }}
          </Button>
          <GalleryActions
            :gid="gallery.gid"
            :token="gallery.token"
            :title="gallery.title"
            source="online"
            density="detail"
            :show-read="false"
            :favorited="favorited"
            :favcat="favcat"
            :in-library="inLibrary"
            :download-status="gallery.download?.status ?? null"
            :download-current-page="gallery.download?.current_page ?? 0"
          />
        </div>
      </template>

      <template #secondary>
        <div v-if="gallery" class="online-detail__links">
          <RouterLink
            v-if="gallery.in_library && gallery.gallery_id"
            class="online-actions__link online-actions__link--outlined"
            :to="{ name: 'gallery', params: { id: gallery.gallery_id } }"
            data-testid="online-open-local"
          >
            {{ t("online.detail.openLocal") }}
          </RouterLink>
          <a
            class="online-actions__link online-actions__link--text"
            :href="officialUrl"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="online-official"
          >
            {{ t("online.detail.openOfficial") }}
            <Icon name="external-link" size="dense" />
          </a>
        </div>
      </template>

      <template #tags>
        <div v-if="gallery" class="online-detail__section">
          <div class="online-detail__head">
            <h2 class="online-detail__title">{{ t("online.detail.tags") }}</h2>
          </div>
          <TagGroups :tags="gallery.tags ?? []" source="online" @select="selectTag" />
        </div>
      </template>

      <template #thumbs>
        <div v-if="gallery" class="online-detail__section">
          <div class="online-detail__head">
            <h2 class="online-detail__title">{{ t("online.detail.thumbs") }}</h2>
            <span class="online-detail__count">
              {{ t("online.detail.pagesCount", { count: gallery.pages }) }}
            </span>
          </div>
          <OnlineThumbGrid
            :gid="gallery.gid"
            :token="gallery.token"
            :total="gallery.pages"
            @select="openPage"
          />
        </div>
      </template>
    </GalleryDetailLayout>
  </section>
</template>

<style scoped>
.online-detail {
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
  min-width: 0;
}

.online-detail__category {
  display: inline-flex;
  align-items: center;
  height: var(--gv-size-tag-lg);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--category-bg, var(--gv-cat-misc));
  color: var(--category-ink, var(--gv-cat-misc-ink));
  font: var(--gv-type-label-small);
}

.online-detail__status {
  display: inline-flex;
  align-items: center;
  height: var(--gv-size-tag-lg);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
  font: var(--gv-type-label-small);
}

/* OD-12: the two navigation entries keep their native link semantics (href /
   target / rel are part of the contract) but are laid out on the same
   control-lg step as every Button in the action row. */
.online-detail__newer,
.online-actions__link {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  height: var(--gv-size-control-lg);
  padding: 0 var(--gv-space-4);
  border: 1px solid transparent;
  border-radius: var(--gv-radius-full);
  font: var(--gv-type-label-large);
  text-decoration: none;
  white-space: nowrap;
}

.online-detail__newer {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.online-actions__link--outlined {
  border-color: var(--gv-color-outline);
  color: var(--gv-color-primary-text);
}

.online-actions__link--text {
  color: var(--gv-color-primary-text);
}

.online-actions__link:hover,
.online-detail__newer:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) var(--gv-state-hover), transparent);
}

.online-actions__link:focus-visible,
.online-detail__newer:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.online-actions,
.online-detail__links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.online-detail__section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  min-width: 0;
}

.online-detail__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.online-detail__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.online-detail__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
