<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import {
  fetchFavoriteDuplicatesStatus,
  ignoreFavoriteDuplicate,
  removeFavorites,
  scanFavoriteDuplicates,
  type FavoriteDuplicateGroup,
  type FavoriteDuplicateItem,
  type FavoriteDuplicatesStatus,
} from "@/api/duplicates";
import { useUiStore } from "@/stores/ui";
import { formatBytes, formatDate } from "@/stores/library";
import { galleryThumbUrl, safeHref } from "@/views/updates/url";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
import MaintenanceTabs from "@/views/updates/components/MaintenanceTabs.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const { t } = useI18n();

type Filter = "all" | "local" | "cloud";
type RemoveMode = "unfav" | "delete";
const FILTERS: readonly Filter[] = ["all", "local", "cloud"];

const status = ref<FavoriteDuplicatesStatus | null>(null);
const loading = ref(true);
const error = ref("");
const scanning = ref(false);
const selected = ref<number[]>([]);
const locallyIgnored = ref<string[]>([]);
const confirmOpen = ref(false);
const removeMode = ref<RemoveMode>("unfav");

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

const filter = computed<Filter>(() => {
  const value = first(route.query.filter);
  return value === "local" || value === "cloud" ? value : "all";
});

function isLocal(item: FavoriteDuplicateItem): boolean {
  return item.gallery_id != null;
}

function applyFilter(groups: FavoriteDuplicateGroup[]): FavoriteDuplicateGroup[] {
  if (filter.value === "all") return groups;
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        filter.value === "local" ? isLocal(item) : !isLocal(item),
      ),
    }))
    .filter((group) => group.items.length > 0);
}

const groups = computed(() => applyFilter(status.value?.groups ?? []));
const itemCount = computed(() =>
  groups.value.reduce((sum, group) => sum + group.items.length, 0),
);
const selectedCount = computed(() => selected.value.length);

function groupTitle(group: FavoriteDuplicateGroup): string {
  const item = group.items[0];
  return item?.display_title || item?.title || group.key;
}

function itemTitle(item: FavoriteDuplicateItem): string {
  return item.display_title || item.title || `gid ${item.gid}`;
}

function itemThumb(item: FavoriteDuplicateItem): string {
  return isLocal(item) && item.gallery_id != null
    ? galleryThumbUrl(item.gallery_id)
    : item.cover_data || item.cover_url || "";
}

function itemLink(item: FavoriteDuplicateItem): string {
  return safeHref(item.url);
}

function isIgnored(group: FavoriteDuplicateGroup): boolean {
  return locallyIgnored.value.includes(group.key);
}

function setFilter(next: Filter): void {
  void router.push({
    name: "favorites-manage",
    query: { ...(next === "all" ? {} : { filter: next }) },
  });
}

function toggle(gid: number): void {
  selected.value = selected.value.includes(gid)
    ? selected.value.filter((value) => value !== gid)
    : [...selected.value, gid];
}

function toggleGroup(group: FavoriteDuplicateGroup): void {
  const gids = group.items.map((item) => item.gid);
  const allSelected = gids.every((gid) => selected.value.includes(gid));
  selected.value = allSelected
    ? selected.value.filter((gid) => !gids.includes(gid))
    : [...new Set([...selected.value, ...gids])];
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function applyStatus(next: FavoriteDuplicatesStatus): void {
  status.value = next;
  const available = new Set(
    (next.groups ?? []).flatMap((group) => group.items.map((item) => item.gid)),
  );
  selected.value = selected.value.filter((gid) => available.has(gid));
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    applyStatus(await fetchFavoriteDuplicatesStatus());
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

async function scan(): Promise<void> {
  if (scanning.value) return;
  scanning.value = true;
  try {
    await scanFavoriteDuplicates();
    for (let index = 0; index < 120; index += 1) {
      await delay(600);
      const next = await fetchFavoriteDuplicatesStatus();
      applyStatus(next);
      if (!next.running) break;
    }
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    scanning.value = false;
  }
}

function openRemove(mode: RemoveMode): void {
  if (!selected.value.length) {
    ui.error(t("maintenance.duplicates.favorites.selectRequired"));
    return;
  }
  removeMode.value = mode;
  confirmOpen.value = true;
}

async function confirmRemove(): Promise<void> {
  const gids = [...selected.value];
  confirmOpen.value = false;
  try {
    const result = await removeFavorites(gids, removeMode.value === "delete");
    const removed = new Set(result.successful_gids ?? gids);
    let message =
      (removeMode.value === "delete"
        ? t("maintenance.duplicates.favorites.confirmDeleteTitle")
        : t("maintenance.duplicates.favorites.unfav")) +
      (result.cloud_ok ? "" : ` · ${t("maintenance.duplicates.favorites.cloudFailed")}`) +
      (result.deleted_local_galleries
        ? t("maintenance.duplicates.favorites.deletedLocal", {
            n: result.deleted_local_galleries,
          })
        : "");
    if (result.failed_deletions?.length) {
      message += ` · ${t("maintenance.duplicates.favorites.deleteFail", { n: result.failed_deletions.length })}`;
    }
    ui.success(message);
    selected.value = [];
    if (status.value) {
      status.value = {
        ...status.value,
        groups: status.value.groups
          .map((group) => ({
            ...group,
            items: group.items.filter((item) => !removed.has(item.gid)),
          }))
          .filter((group) => group.items.length > 0),
      };
    }
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function ignoreSelected(): Promise<void> {
  if (!selected.value.length) {
    ui.error(t("maintenance.duplicates.favorites.selectRequired"));
    return;
  }
  const chosen = new Set(selected.value);
  const targets = (status.value?.groups ?? []).filter((group) =>
    group.items.some((item) => chosen.has(item.gid)),
  );
  let ok = 0;
  for (const group of targets) {
    try {
      await ignoreFavoriteDuplicate({
        key: group.key,
        title: groupTitle(group),
        gids: group.items.map((item) => item.gid),
      });
      locallyIgnored.value = [...new Set([...locallyIgnored.value, group.key])];
      ok += 1;
    } catch {
      /* keep going; the summary below reports the successful count */
    }
  }
  selected.value = [];
  ui.success(t("maintenance.duplicates.favorites.ignoredOk", { n: ok }));
}

function clearSelection(): void {
  selected.value = [];
}

const confirmTitle = computed(() =>
  removeMode.value === "delete"
    ? t("maintenance.duplicates.favorites.confirmDeleteTitle")
    : t("maintenance.duplicates.favorites.confirmUnfavTitle"),
);
const confirmBody = computed(() =>
  removeMode.value === "delete"
    ? t("maintenance.duplicates.favorites.confirmDeleteBody", { n: selectedCount.value })
    : t("maintenance.duplicates.favorites.confirmUnfavBody", { n: selectedCount.value }),
);

onMounted(load);
</script>

<template>
  <section class="favdup" data-testid="dupfav-view">
    <header class="favdup__header">
      <p class="favdup__eyebrow">{{ t("maintenance.duplicates.favorites.eyebrow") }}</p>
      <h1 class="favdup__title">{{ t("maintenance.duplicates.favorites.title") }}</h1>
      <p class="favdup__subtitle">{{ t("maintenance.duplicates.favorites.subtitle") }}</p>
    </header>

    <MaintenanceTabs active="favmanage" />

    <div class="favdup__toolbar">
      <Button data-testid="dupfav-scan" :loading="scanning" @click="scan">
        {{
          scanning
            ? t("maintenance.duplicates.favorites.scanning")
            : t("maintenance.duplicates.favorites.scan")
        }}
      </Button>
      <Button
        v-for="item in FILTERS"
        :key="item"
        size="compact"
        :variant="filter === item ? 'tonal' : 'outlined'"
        :data-testid="`dupfav-filter-${item}`"
        @click="setFilter(item)"
      >
        {{
          item === "all"
            ? t("maintenance.duplicates.favorites.filterAll")
            : item === "local"
              ? t("maintenance.duplicates.favorites.filterLocal")
              : t("maintenance.duplicates.favorites.filterCloud")
        }}
      </Button>
      <Button
        variant="outlined"
        class="favdup__danger"
        data-testid="dupfav-unfav"
        :disabled="!selectedCount"
        @click="openRemove('unfav')"
      >
        {{ t("maintenance.duplicates.favorites.unfav") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
      <Button
        variant="outlined"
        class="favdup__danger"
        data-testid="dupfav-unfav-delete"
        :disabled="!selectedCount"
        @click="openRemove('delete')"
      >
        {{ t("maintenance.duplicates.favorites.unfavDelete") }}
      </Button>
      <Button
        variant="outlined"
        data-testid="dupfav-ignore"
        :disabled="!selectedCount"
        @click="ignoreSelected"
      >
        {{ t("maintenance.duplicates.favorites.ignoreSelected") }}
      </Button>
      <Button variant="text" data-testid="dupfav-clear" @click="clearSelection">
        {{ t("maintenance.duplicates.favorites.clear") }}
      </Button>
      <RouterLink class="favdup__link" :to="{ name: 'favorites-ignored' }">
        {{ t("maintenance.duplicates.favorites.ignoredPageLink") }}
      </RouterLink>
    </div>

    <div v-if="status?.running" class="favdup__progress" data-testid="dupfav-progress">
      <span class="favdup__progress-bar">
        <span
          class="favdup__progress-fill"
          :style="{
            width: `${status.total ? Math.min(100, Math.round((status.done / status.total) * 100)) : 0}%`,
          }"
        />
      </span>
      <span class="favdup__progress-text">
        {{
          t("maintenance.duplicates.favorites.progress", {
            stage: status.stage ?? "",
            done: status.done,
            total: status.total,
          })
        }}
      </span>
    </div>

    <div v-if="loading" class="favdup__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 4" :key="index" variant="list" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <template v-else>
      <p v-if="status?.last_error" class="favdup__error" role="alert">
        {{ status.last_error }}
      </p>

      <EmptyState
        v-if="!groups.length"
        :title="status ? t('maintenance.duplicates.favorites.none') : t('maintenance.duplicates.favorites.hint')"
        testid="dupfav-empty"
      />

      <template v-else>
        <p class="favdup__summary" data-testid="dupfav-summary">
          {{
            t("maintenance.duplicates.favorites.found", {
              groups: groups.length,
              items: itemCount,
            })
          }}
        </p>

        <article
          v-for="group in groups"
          :key="group.key"
          class="favdup__group"
          :class="{ 'favdup__group--ignored': isIgnored(group) }"
          :data-testid="`dupfav-group-${group.key}`"
        >
          <header class="favdup__group-head">
            <span class="favdup__count">{{ group.items.length }} ×</span>
            <span class="favdup__group-title">{{ groupTitle(group) }}</span>
            <span v-if="group.artist" class="favdup__artist">{{ group.artist }}</span>
            <span v-if="isIgnored(group)" class="favdup__badge">
              {{ t("maintenance.duplicates.favorites.ignored") }}
            </span>
            <span class="favdup__group-actions">
              <Button
                variant="outlined"
                size="compact"
                data-testid="dupfav-select-group"
                @click="toggleGroup(group)"
              >
                {{ t("maintenance.shared.select") }}
              </Button>
            </span>
          </header>

          <div
            v-for="item in group.items"
            :key="item.gid"
            class="favdup__row"
            :data-testid="`dupfav-item-${item.gid}`"
          >
            <label class="favdup__check">
              <input
                type="checkbox"
                :checked="selected.includes(item.gid)"
                :aria-label="t('maintenance.shared.select')"
                :data-testid="`dupfav-select-${item.gid}`"
                @change="toggle(item.gid)"
              />
              <GalleryThumb :src="itemThumb(item)" :alt="itemTitle(item)" />
              <span class="favdup__body">
                <RouterLink
                  v-if="isLocal(item)"
                  class="favdup__item-title"
                  :to="{ name: 'gallery', params: { id: item.gallery_id } }"
                >
                  {{ itemTitle(item) }}
                </RouterLink>
                <a
                  v-else
                  class="favdup__item-title"
                  :href="itemLink(item)"
                  target="_blank"
                  rel="noopener"
                >
                  {{ itemTitle(item) }}
                </a>
                <span class="favdup__meta">
                  <span class="favdup__badge">
                    {{
                      isLocal(item)
                        ? t("maintenance.duplicates.library.current")
                        : t("maintenance.duplicates.favorites.filterCloud")
                    }}
                  </span>
                  <span v-if="item.favcat != null" class="favdup__badge">
                    #{{ item.favcat }}
                  </span>
                  <span v-if="item.posted_at" class="favdup__badge">
                    {{ formatDate(item.posted_at) }}
                  </span>
                  <span v-if="item.file_size" class="favdup__badge">
                    {{ formatBytes(item.file_size) }}
                  </span>
                </span>
                <span v-if="item.tags?.length" class="favdup__tags">
                  <span
                    v-for="tag in item.tags"
                    :key="`${tag.namespace}:${tag.name}`"
                    class="favdup__tag"
                  >
                    {{ tag.display || tag.name }}
                  </span>
                </span>
              </span>
            </label>
          </div>
        </article>
      </template>
    </template>

    <ConfirmDialog
      :open="confirmOpen"
      :title="confirmTitle"
      :body="confirmBody"
      :confirm-label="
        removeMode === 'delete'
          ? t('maintenance.duplicates.favorites.unfavDelete')
          : t('maintenance.duplicates.favorites.unfav')
      "
      danger
      testid="dupfav-confirm"
      @confirm="confirmRemove"
      @cancel="confirmOpen = false"
    />
  </section>
</template>

<style scoped>
.favdup {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.favdup__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favdup__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.favdup__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.favdup__subtitle,
.favdup__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.favdup__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.favdup__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.favdup__link {
  margin-left: auto;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.favdup__danger {
  border-color: var(--gv-color-error);
  color: var(--gv-color-error);
}

.favdup__progress {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favdup__progress-bar {
  display: block;
  height: var(--gv-space-1);
  overflow: hidden;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.favdup__progress-fill {
  display: block;
  height: 100%;
  background: var(--gv-color-primary);
  transition: width var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.favdup__progress-text {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.favdup__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.favdup__group {
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.favdup__group--ignored {
  opacity: 0.72;
}

.favdup__group-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.favdup__count {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.favdup__group-title {
  min-width: 0;
  overflow: hidden;
  flex: 1;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.favdup__artist {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.favdup__group-actions {
  display: flex;
  gap: var(--gv-space-2);
}

.favdup__row {
  padding-top: var(--gv-space-3);
}

.favdup__check {
  display: flex;
  align-items: flex-start;
  gap: var(--gv-space-3);
}

.favdup__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favdup__item-title {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.favdup__meta,
.favdup__tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.favdup__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.favdup__tag {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

@media (max-width: 599px) {
  .favdup__link {
    margin-left: 0;
  }
}
</style>
