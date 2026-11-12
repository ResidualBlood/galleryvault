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
import GalleryActions from "@/components/actions/GalleryActions.vue";
import GalleryDetailLayout from "@/components/gallery/GalleryDetailLayout.vue";
import TagGroups from "@/components/gallery/TagGroups.vue";
import { useViewRequest } from "@/composables/useViewRequest";
import { formatBytes, formatDate } from "@/stores/library";
import { useFavoritesStore } from "@/stores/favorites";
import { useDownloadsStore } from "@/stores/downloads";
import { useUiStore } from "@/stores/ui";
import { categoryToken } from "@/views/online/list/category";
import OnlineStateNotice from "@/views/online/list/OnlineStateNotice.vue";
import { ensureOnlineMessages } from "@/views/online/list/messages";
import OnlineThumbGrid from "./OnlineThumbGrid.vue";
import "@/views/gallery/i18n";

ensureOnlineMessages();

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const favorites = useFavoritesStore();
const downloads = useDownloadsStore();
const request = useViewRequest();
const { t, te } = useI18n();

const gallery = ref<OnlineGallery | null>(null);
const state = ref<OnlineState>("ok");
const loading = ref(true);
const error = ref(false);
const coverFailed = ref(false);

const status = computed<"loading" | "ready" | "error">(() => {
  if (loading.value) return "loading";
  if (error.value) return "error";
  return "ready";
});

const showState = computed(
  () => !loading.value && !error.value && state.value !== "ok",
);

const subtitle = computed(() => {
  const item = gallery.value;
  if (!item || !item.title_jpn || item.title_jpn === item.title) return "";
  return item.title_jpn;
});

const coverUrl = computed(() => {
  const url = gallery.value?.thumb?.trim() ?? "";
  return /^https?:\/\//i.test(url) ? url : "";
});

const posted = computed(() => formatDate(gallery.value?.posted));
const size = computed(() => formatBytes(gallery.value?.file_size));
const rating = computed(() => {
  const value = gallery.value?.rating;
  return typeof value === "number" ? value.toFixed(1) : "";
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
  const q = tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name;
  void router.push({ name: "online", query: { q } });
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
  coverFailed.value = false;
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
      :error-title="t('online.detail.loadFailed')"
      @retry="load"
    >
      <template #header>
        <article v-if="gallery" class="online-header">
          <div class="online-header__cover">
            <img
              v-if="coverUrl && !coverFailed"
              class="online-header__image"
              data-testid="online-cover"
              :src="coverUrl"
              :alt="t('online.detail.coverAlt', { title: gallery.title })"
              referrerpolicy="no-referrer"
              decoding="async"
              @error="coverFailed = true"
            />
            <div v-else class="online-header__fallback" data-testid="online-cover-fallback">
              <span>{{ t("online.detail.coverMissing") }}</span>
            </div>
          </div>

          <div class="online-header__info">
            <span class="online-header__category" :style="categoryStyle">
              {{ categoryLabel }}
            </span>
            <h1 class="online-header__title" data-testid="online-title">
              {{ gallery.title }}
            </h1>
            <p v-if="subtitle" class="online-header__subtitle" data-testid="online-subtitle">
              {{ subtitle }}
            </p>

            <dl class="online-header__meta">
              <div class="online-header__meta-item">
                <dt>{{ t("online.detail.uploader") }}</dt>
                <dd>{{ gallery.uploader || t("online.detail.unknown") }}</dd>
              </div>
              <div class="online-header__meta-item">
                <dt>{{ t("online.detail.posted") }}</dt>
                <dd>{{ posted || t("online.detail.unknown") }}</dd>
              </div>
              <div class="online-header__meta-item">
                <dt>{{ t("online.detail.pages") }}</dt>
                <dd>{{ gallery.pages }}</dd>
              </div>
              <div class="online-header__meta-item">
                <dt>{{ t("online.detail.size") }}</dt>
                <dd>{{ size || t("online.detail.unknown") }}</dd>
              </div>
              <div class="online-header__meta-item">
                <dt>{{ t("online.detail.rating") }}</dt>
                <dd>{{ rating || t("online.detail.unknown") }}</dd>
              </div>
              <div v-if="favorited" class="online-header__meta-item">
                <dt>{{ t("online.detail.favorite") }}</dt>
                <dd>{{ t("online.detail.favcat", { cat: favcat ?? 0 }) }}</dd>
              </div>
            </dl>

            <RouterLink
              v-if="gallery.newer"
              class="online-header__newer"
              :to="{
                name: 'online-detail',
                params: { gid: gallery.newer.gid, token: gallery.newer.token },
              }"
              data-testid="online-newer"
            >
              ⤴ {{ t("online.detail.newer") }}
            </RouterLink>

            <p v-if="inLibrary" class="online-header__in-library" data-testid="online-in-library">
              {{ t("online.detail.inLibrary") }}
            </p>
          </div>
        </article>
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
            :download-total-pages="gallery.download?.total_pages ?? null"
          />
          <RouterLink
            v-if="gallery.in_library && gallery.gallery_id"
            class="online-actions__link"
            :to="{ name: 'gallery', params: { id: gallery.gallery_id } }"
            data-testid="online-open-local"
          >
            {{ t("online.detail.openLocal") }}
          </RouterLink>
          <a
            class="online-actions__link"
            :href="officialUrl"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="online-official"
          >
            {{ t("online.detail.openOfficial") }}
          </a>
        </div>
      </template>

      <template #tags>
        <div v-if="gallery" class="online-section">
          <div class="online-section__head">
            <h2 class="online-section__title">{{ t("online.detail.tags") }}</h2>
          </div>
          <TagGroups :tags="gallery.tags ?? []" @select="selectTag" />
        </div>
      </template>

      <template #thumbs>
        <div v-if="gallery" class="online-section">
          <div class="online-section__head">
            <h2 class="online-section__title">{{ t("online.detail.thumbs") }}</h2>
            <span class="online-section__count">
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
}

.online-header {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--gv-space-4);
}

.online-header__cover {
  width: min(180px, 45vw);
}

.online-header__image,
.online-header__fallback {
  display: block;
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-highest);
}

.online-header__image {
  object-fit: cover;
}

.online-header__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-align: center;
}

.online-header__info {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.online-header__category {
  align-self: flex-start;
  height: 24px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--category-bg, var(--gv-cat-misc));
  color: var(--category-ink, var(--gv-cat-misc-ink));
  font: var(--gv-type-label-small);
  line-height: 24px;
}

.online-header__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
  overflow-wrap: anywhere;
}

.online-header__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
  overflow-wrap: anywhere;
}

.online-header__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--gv-space-2) var(--gv-space-4);
  margin: var(--gv-space-2) 0 0;
}

.online-header__meta-item {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.online-header__meta-item dt {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-medium);
}

.online-header__meta-item dd {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  overflow-wrap: anywhere;
}

.online-header__newer {
  align-self: flex-start;
  padding: var(--gv-space-1) var(--gv-space-3);
  border: 1px solid var(--gv-color-warning);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-warning);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.online-header__in-library {
  margin: 0;
  color: var(--gv-color-success);
  font: var(--gv-type-label-large);
}

.online-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.online-actions__link {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.online-actions__link:hover {
  background: var(--gv-color-surface-container-high);
}

.online-actions__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.online-section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.online-section__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.online-section__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.online-section__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

@media (min-width: 840px) {
  .online-header {
    grid-template-columns: 176px minmax(0, 1fr);
  }

  .online-header__cover {
    width: 176px;
  }
}
</style>
