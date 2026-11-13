<!-- gv-polish:pending -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import {
  fetchIgnoredFavoriteDuplicates,
  unignoreFavoriteDuplicate,
  type FavoriteDuplicateItem,
  type IgnoredFavoriteDuplicate,
} from "@/api/duplicates";
import { useUiStore } from "@/stores/ui";
import { formatBytes, formatDate } from "@/stores/library";
import { galleryThumbUrl, safeHref } from "@/views/updates/url";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const ui = useUiStore();
const { t } = useI18n();

const entries = ref<IgnoredFavoriteDuplicate[]>([]);
const selected = ref<string[]>([]);
const loading = ref(true);
const error = ref("");

function isLocal(item: FavoriteDuplicateItem): boolean {
  return item.gallery_id != null;
}

function itemTitle(item: FavoriteDuplicateItem): string {
  return item.display_title || item.title || `gid ${item.gid}`;
}

function itemThumb(item: FavoriteDuplicateItem): string {
  return isLocal(item) && item.gallery_id != null
    ? galleryThumbUrl(item.gallery_id)
    : item.cover_data || item.cover_url || "";
}

function toggle(key: string): void {
  selected.value = selected.value.includes(key)
    ? selected.value.filter((value) => value !== key)
    : [...selected.value, key];
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchIgnoredFavoriteDuplicates();
    entries.value = Array.isArray(data) ? data : [];
    const available = new Set(entries.value.map((entry) => entry.key));
    selected.value = selected.value.filter((key) => available.has(key));
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

async function restore(keys: string[]): Promise<void> {
  if (!keys.length) {
    ui.error(t("maintenance.duplicates.favorites.selectRequired"));
    return;
  }
  let ok = 0;
  for (const key of keys) {
    try {
      await unignoreFavoriteDuplicate(key);
      ok += 1;
    } catch {
      /* report only the successful count below */
    }
  }
  ui.success(t("maintenance.duplicates.favorites.ignoredPage.restored", { n: ok }));
  selected.value = [];
  await load();
}

onMounted(load);
</script>

<template>
  <section class="favignored" data-testid="favignored-view">
    <header class="favignored__header">
      <p class="favignored__eyebrow">{{ t("maintenance.duplicates.favorites.eyebrow") }}</p>
      <h1 class="favignored__title">
        {{ t("maintenance.duplicates.favorites.ignoredPage.title") }}
      </h1>
      <p class="favignored__subtitle">
        {{ t("maintenance.duplicates.favorites.ignoredPage.subtitle") }}
      </p>
    </header>

    <MaintenanceTabs active="favmanage" />

    <div class="favignored__toolbar">
      <Button
        data-testid="favignored-restore-selected"
        :disabled="!selected.length"
        @click="restore(selected)"
      >
        {{ t("maintenance.duplicates.favorites.ignoredPage.unignoreSelected") }}
      </Button>
      <RouterLink class="favignored__link" :to="{ name: 'favorites-manage' }">
        {{ t("maintenance.duplicates.favorites.title") }}
      </RouterLink>
    </div>

    <div v-if="loading" class="favignored__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 3" :key="index" variant="list" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!entries.length"
      :title="t('maintenance.duplicates.favorites.ignoredPage.empty')"
      testid="favignored-empty"
    />

    <template v-else>
      <article
        v-for="(entry, index) in entries"
        :key="entry.key"
        class="favignored__group"
        :data-testid="`favignored-group-${index}`"
      >
      <header class="favignored__group-head">
        <label class="favignored__check">
          <input
            type="checkbox"
            :checked="selected.includes(entry.key)"
            :aria-label="t('maintenance.shared.select')"
            :data-testid="`favignored-select-${index}`"
            @change="toggle(entry.key)"
          />
          <strong>{{ entry.items?.length ?? entry.gids?.length ?? 0 }} ×</strong>
          <span class="favignored__group-title">{{ entry.title || entry.key }}</span>
        </label>
        <Button
          variant="outlined"
          size="compact"
          data-testid="favignored-restore-one"
          @click="restore([entry.key])"
        >
          {{ t("maintenance.duplicates.favorites.ignoredPage.unignore") }}
        </Button>
      </header>

      <div
        v-for="item in entry.items"
        :key="item.gid"
        class="favignored__row"
        :data-testid="`favignored-item-${item.gid}`"
      >
        <GalleryThumb :src="itemThumb(item)" :alt="itemTitle(item)" />
        <div class="favignored__body">
          <RouterLink
            v-if="isLocal(item)"
            class="favignored__item-title"
            :to="{ name: 'gallery', params: { id: item.gallery_id } }"
          >
            {{ itemTitle(item) }}
          </RouterLink>
          <a
            v-else
            class="favignored__item-title"
            :href="safeHref(item.url)"
            target="_blank"
            rel="noopener"
          >
            {{ itemTitle(item) }}
          </a>
          <div class="favignored__meta">
            <span class="favignored__badge">
              {{
                isLocal(item)
                  ? t("maintenance.duplicates.library.current")
                  : t("maintenance.duplicates.favorites.filterCloud")
              }}
            </span>
            <span v-if="item.favcat != null" class="favignored__badge">#{{ item.favcat }}</span>
            <span v-if="item.posted_at" class="favignored__badge">
              {{ formatDate(item.posted_at) }}
            </span>
            <span v-if="item.file_size" class="favignored__badge">
              {{ formatBytes(item.file_size) }}
            </span>
          </div>
        </div>
      </div>
      </article>
    </template>
  </section>
</template>

<style scoped>
.favignored {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.favignored__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favignored__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.favignored__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.favignored__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.favignored__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.favignored__link {
  margin-left: auto;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.favignored__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.favignored__group {
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.favignored__group-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-3);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.favignored__check {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: var(--gv-space-2);
}

.favignored__group-title {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.favignored__row {
  display: flex;
  gap: var(--gv-space-3);
  padding-top: var(--gv-space-3);
}

.favignored__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favignored__item-title {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.favignored__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.favignored__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

@media (max-width: 599px) {
  .favignored__link {
    margin-left: 0;
  }
}
</style>
