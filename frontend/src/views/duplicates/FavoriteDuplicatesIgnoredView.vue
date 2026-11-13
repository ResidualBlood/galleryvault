<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import DuplicateBadge from "./components/DuplicateBadge.vue";
import DuplicateCopyRow from "./components/DuplicateCopyRow.vue";
import DuplicateGroupCard from "./components/DuplicateGroupCard.vue";
import {
  fetchIgnoredFavoriteDuplicates,
  unignoreFavoriteDuplicate,
  type FavoriteDuplicateItem,
  type IgnoredFavoriteDuplicate,
} from "@/api/duplicates";
import { useUiStore } from "@/stores/ui";
import { formatBytes, formatDate } from "@/stores/library";
import { galleryThumbUrl } from "@/views/updates/url";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const router = useRouter();
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

function itemTo(item: FavoriteDuplicateItem) {
  return isLocal(item) ? { name: "gallery", params: { id: item.gallery_id } } : null;
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

function back(): void {
  void router.push({ name: "favorites-manage" });
}

const crumbs = computed(() => [
  {
    label: t("maintenance.duplicates.favorites.title"),
    to: "/duplicates/favorites",
  },
  { label: t("maintenance.duplicates.favorites.ignoredPage.title") },
]);
const selectedCount = computed(() => selected.value.length);

onMounted(load);
</script>

<template>
  <section class="favignored" data-testid="favignored-view">
    <PageHeader
      :title="t('maintenance.duplicates.favorites.ignoredPage.title')"
      :count="entries.length"
      :subtitle="t('maintenance.duplicates.favorites.ignoredPage.subtitle')"
      :crumbs="crumbs"
      back
      :back-label="t('maintenance.duplicates.favorites.ignoredPage.back')"
      testid="favignored-header"
      @back="back"
    />

    <SelectionBar
      :count="selectedCount"
      :label="t('maintenance.shared.selected', { n: selectedCount })"
      testid="favignored-selection"
      @clear="selected = []"
    >
      <Button
        variant="tonal"
        icon="retry"
        data-testid="favignored-restore-selected"
        @click="restore(selected)"
      >
        {{ t("maintenance.duplicates.favorites.ignoredPage.unignoreSelected") }}
      </Button>
    </SelectionBar>

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
      icon="status-blocked"
      :title="t('maintenance.duplicates.favorites.ignoredPage.empty')"
      :body="t('maintenance.duplicates.favorites.ignoredPage.emptyBody')"
      :action-label="t('maintenance.duplicates.favorites.ignoredPage.back')"
      testid="favignored-empty"
      @action="back"
    />

    <template v-else>
      <DuplicateGroupCard
        v-for="(entry, index) in entries"
        :key="entry.key"
        :title="entry.title || entry.key"
        :testid="`favignored-group-${index}`"
      >
        <template #badges>
          <DuplicateBadge size="sm" tone="primary">
            {{ entry.items?.length ?? entry.gids?.length ?? 0 }}
          </DuplicateBadge>
        </template>
        <template #actions>
          <Button
            :variant="selected.includes(entry.key) ? 'tonal' : 'outlined'"
            size="sm"
            :icon="selected.includes(entry.key) ? 'check' : 'all-selected'"
            :aria-pressed="selected.includes(entry.key)"
            :data-testid="`favignored-select-${index}`"
            @click="toggle(entry.key)"
          >
            {{ t("maintenance.shared.select") }}
          </Button>
          <Button
            variant="outlined"
            size="sm"
            icon="retry"
            data-testid="favignored-restore-one"
            @click="restore([entry.key])"
          >
            {{ t("maintenance.duplicates.favorites.ignoredPage.unignore") }}
          </Button>
        </template>

        <DuplicateCopyRow
          v-for="item in entry.items"
          :key="item.gid"
          :title="itemTitle(item)"
          :thumb="itemThumb(item)"
          :to="itemTo(item)"
          :href="isLocal(item) ? null : item.url"
          :tags="item.tags ?? []"
          :testid="`favignored-item-${item.gid}`"
        >
          <template #meta>
            <DuplicateBadge>
              {{
                isLocal(item)
                  ? t("maintenance.duplicates.library.current")
                  : t("maintenance.duplicates.favorites.filterCloud")
              }}
            </DuplicateBadge>
            <DuplicateBadge v-if="item.favcat != null">#{{ item.favcat }}</DuplicateBadge>
            <DuplicateBadge v-if="item.posted_at">{{ formatDate(item.posted_at) }}</DuplicateBadge>
            <DuplicateBadge v-if="item.file_size">{{ formatBytes(item.file_size) }}</DuplicateBadge>
          </template>
        </DuplicateCopyRow>
      </DuplicateGroupCard>
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

.favignored__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}
</style>
