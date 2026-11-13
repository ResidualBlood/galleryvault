<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import {
  fetchCrossGidDuplicates,
  ignoreFavoriteDuplicate,
  refreshCrossGidDuplicates,
  removeFavorites,
  type CrossGidGroup,
  type CrossGidItem,
  type CrossGidResponse,
} from "@/api/duplicates";
import { useUiStore } from "@/stores/ui";
import { formatBytes } from "@/stores/library";
import { galleryThumbUrl, safeHref } from "@/views/updates/url";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
import PagerBar from "@/views/updates/components/PagerBar.vue";
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
const PAGE_SIZE = 24;

const response = ref<CrossGidResponse | null>(null);
const loading = ref(true);
const error = ref("");
const busy = ref(false);
const selected = ref<number[]>([]);
const ignoredKeys = ref<string[]>([]);
const collapsed = ref<string[]>([]);
const confirmOpen = ref(false);
const removeMode = ref<RemoveMode>("unfav");
let seq = 0;

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

const filter = computed<Filter>(() => {
  const value = first(route.query.filter);
  return value === "local" || value === "cloud" ? value : "all";
});
const page = computed(() => {
  const parsed = Number.parseInt(first(route.query.page), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
});

function isLocal(item: CrossGidItem): boolean {
  return item.gallery_id != null;
}

function applyFilter(groups: CrossGidGroup[]): CrossGidGroup[] {
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

const groups = computed(() => applyFilter(response.value?.groups ?? []));
const totalPages = computed(() => Math.max(1, Math.ceil(groups.value.length / PAGE_SIZE)));
const pageGroups = computed(() =>
  groups.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
);
const selectedCount = computed(() => selected.value.length);
const favoritedSelected = computed(() => {
  const chosen = new Set(selected.value);
  return (response.value?.groups ?? [])
    .flatMap((group) => group.items)
    .filter((item) => chosen.has(item.gid) && item.favorited)
    .map((item) => item.gid);
});

function groupTitle(group: CrossGidGroup): string {
  const item = group.items[0];
  return item?.display_title || item?.title || group.key;
}

function itemTitle(item: CrossGidItem): string {
  return item.display_title || item.title || `gid ${item.gid}`;
}

function itemThumb(item: CrossGidItem): string {
  if (isLocal(item) && item.gallery_id != null) return galleryThumbUrl(item.gallery_id);
  return item.cover_url || item.cover_data || "";
}

function isIgnored(group: CrossGidGroup): boolean {
  return ignoredKeys.value.includes(group.key);
}

function isCollapsed(group: CrossGidGroup): boolean {
  return collapsed.value.includes(group.key);
}

function toggleCollapsed(group: CrossGidGroup): void {
  collapsed.value = isCollapsed(group)
    ? collapsed.value.filter((key) => key !== group.key)
    : [...collapsed.value, group.key];
}

function setFilter(next: Filter): void {
  void router.push({
    name: "duplicates-cross-gid",
    query: next === "all" ? {} : { filter: next },
  });
}

function goPage(next: number): void {
  void router.push({
    name: "duplicates-cross-gid",
    query: { ...(filter.value === "all" ? {} : { filter: filter.value }), page: next },
  });
}

function toggle(gid: number): void {
  selected.value = selected.value.includes(gid)
    ? selected.value.filter((value) => value !== gid)
    : [...selected.value, gid];
}

function toggleGroup(group: CrossGidGroup): void {
  const gids = group.items.map((item) => item.gid);
  const allSelected = gids.every((gid) => selected.value.includes(gid));
  selected.value = allSelected
    ? selected.value.filter((gid) => !gids.includes(gid))
    : [...new Set([...selected.value, ...gids])];
}

function applyResponse(data: CrossGidResponse): void {
  response.value = data;
  const available = new Set(
    (data.groups ?? []).flatMap((group) => group.items.map((item) => item.gid)),
  );
  selected.value = selected.value.filter((gid) => available.has(gid));
}

async function load(): Promise<void> {
  const token = ++seq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchCrossGidDuplicates();
    if (token !== seq) return;
    applyResponse(data);
  } catch (cause) {
    if (token !== seq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (token === seq) loading.value = false;
  }
}

async function recompute(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    applyResponse(await refreshCrossGidDuplicates());
    selected.value = [];
    void router.push({ name: "duplicates-cross-gid" });
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}

function openRemove(mode: RemoveMode): void {
  if (!selected.value.length) {
    ui.error(t("maintenance.duplicates.favorites.selectRequired"));
    return;
  }
  if (!favoritedSelected.value.length) {
    ui.error(t("maintenance.duplicates.cross.noFav"));
    return;
  }
  removeMode.value = mode;
  confirmOpen.value = true;
}

async function confirmRemove(): Promise<void> {
  const gids = [...favoritedSelected.value];
  confirmOpen.value = false;
  try {
    const result = await removeFavorites(gids, removeMode.value === "delete");
    const removed = new Set(result.successful_gids ?? gids);
    let message =
      removeMode.value === "delete"
        ? t("maintenance.duplicates.favorites.unfavDelete")
        : t("maintenance.duplicates.favorites.unfav");
    if (!result.cloud_ok) message += ` · ${t("maintenance.duplicates.favorites.cloudFailed")}`;
    if (result.deleted_local_galleries) {
      message += t("maintenance.duplicates.favorites.deletedLocal", {
        n: result.deleted_local_galleries,
      });
    }
    if (result.failed_deletions?.length) {
      message += ` · ${t("maintenance.duplicates.favorites.deleteFail", { n: result.failed_deletions.length })}`;
    }
    ui.success(message);
    selected.value = [];
    if (response.value) {
      response.value = {
        ...response.value,
        groups: response.value.groups
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
  const targets = (response.value?.groups ?? []).filter((group) =>
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
      ignoredKeys.value = [...new Set([...ignoredKeys.value, group.key])];
      ok += 1;
    } catch {
      /* keep going; the summary reports how many groups were ignored */
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
    ? t("maintenance.duplicates.favorites.confirmDeleteBody", {
        n: favoritedSelected.value.length,
      })
    : t("maintenance.duplicates.favorites.confirmUnfavBody", {
        n: favoritedSelected.value.length,
      }),
);

watch(
  () => filter.value,
  () => {
    selected.value = [];
  },
);

onMounted(load);
</script>

<template>
  <section class="xgid" data-testid="dupxgid-view">
    <header class="xgid__header">
      <p class="xgid__eyebrow">{{ t("maintenance.duplicates.cross.eyebrow") }}</p>
      <h1 class="xgid__title">{{ t("maintenance.duplicates.cross.title") }}</h1>
      <p class="xgid__subtitle">{{ t("maintenance.duplicates.cross.subtitle") }}</p>
    </header>

    <MaintenanceTabs active="dupxgid" />

    <div class="xgid__toolbar">
      <Button data-testid="dupxgid-recompute" :loading="busy" @click="recompute">
        {{ t("maintenance.duplicates.cross.recompute") }}
      </Button>
      <Button variant="outlined" data-testid="dupxgid-refresh" @click="load">
        {{ t("maintenance.duplicates.cross.refresh") }}
      </Button>
      <Button
        v-for="item in FILTERS"
        :key="item"
        size="compact"
        :variant="filter === item ? 'tonal' : 'outlined'"
        :data-testid="`dupxgid-filter-${item}`"
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
        class="xgid__danger"
        data-testid="dupxgid-unfav"
        :disabled="!selectedCount"
        @click="openRemove('unfav')"
      >
        {{ t("maintenance.duplicates.favorites.unfav") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
      <Button
        variant="outlined"
        class="xgid__danger"
        data-testid="dupxgid-unfav-delete"
        :disabled="!selectedCount"
        @click="openRemove('delete')"
      >
        {{ t("maintenance.duplicates.favorites.unfavDelete") }}
      </Button>
      <Button
        variant="outlined"
        data-testid="dupxgid-ignore"
        :disabled="!selectedCount"
        @click="ignoreSelected"
      >
        {{ t("maintenance.duplicates.favorites.ignoreSelected") }}
      </Button>
      <Button variant="text" data-testid="dupxgid-clear" @click="clearSelection">
        {{ t("maintenance.duplicates.favorites.clear") }}
      </Button>
      <RouterLink class="xgid__link" :to="{ name: 'favorites-ignored' }">
        {{ t("maintenance.duplicates.favorites.ignoredPageLink") }}
      </RouterLink>
    </div>

    <details class="xgid__info">
      <summary>{{ t("maintenance.duplicates.cross.infoSummary") }}</summary>
      <p>{{ t("maintenance.duplicates.cross.infoDetail") }}</p>
    </details>

    <div v-if="loading" class="xgid__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 4" :key="index" variant="list" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!response?.ready"
      :title="t('maintenance.duplicates.cross.hint')"
      testid="dupxgid-hint"
    />

    <EmptyState
      v-else-if="!groups.length"
      :title="t('maintenance.duplicates.cross.none')"
      testid="dupxgid-empty"
    />

    <template v-else>
      <p class="xgid__summary" data-testid="dupxgid-summary">
        {{
          t("maintenance.duplicates.favorites.found", {
            groups: groups.length,
            items: groups.reduce((sum, group) => sum + group.items.length, 0),
          })
        }}
      </p>

      <article
        v-for="group in pageGroups"
        :key="group.key"
        class="xgid__group"
        :class="{ 'xgid__group--ignored': isIgnored(group) }"
        :data-testid="`dupxgid-group-${group.key}`"
      >
        <header class="xgid__group-head">
          <span class="xgid__count">{{ group.items.length }} ×</span>
          <span class="xgid__group-title">{{ groupTitle(group) }}</span>
          <span v-if="group.artist" class="xgid__artist">{{ group.artist }}</span>
          <span v-if="isIgnored(group)" class="xgid__badge">
            {{ t("maintenance.duplicates.favorites.ignored") }}
          </span>
          <span class="xgid__group-actions">
            <Button
              variant="outlined"
              size="compact"
              data-testid="dupxgid-select-group"
              @click="toggleGroup(group)"
            >
              {{ t("maintenance.shared.select") }}
            </Button>
            <Button
              variant="text"
              size="compact"
              :aria-expanded="!isCollapsed(group)"
              data-testid="dupxgid-collapse"
              @click="toggleCollapsed(group)"
            >
              ⇕
            </Button>
          </span>
        </header>

        <div v-show="!isCollapsed(group)">
          <div
            v-for="item in group.items"
            :key="item.gid"
            class="xgid__row"
            :data-testid="`dupxgid-item-${item.gid}`"
          >
            <label class="xgid__check">
              <input
                type="checkbox"
                :checked="selected.includes(item.gid)"
                :aria-label="t('maintenance.shared.select')"
                :data-testid="`dupxgid-select-${item.gid}`"
                @change="toggle(item.gid)"
              />
              <GalleryThumb :src="itemThumb(item)" :alt="itemTitle(item)" />
              <span class="xgid__body">
                <RouterLink
                  v-if="isLocal(item)"
                  class="xgid__item-title"
                  :to="{ name: 'gallery', params: { id: item.gallery_id } }"
                >
                  {{ itemTitle(item) }}
                </RouterLink>
                <a
                  v-else
                  class="xgid__item-title"
                  :href="safeHref(item.url)"
                  target="_blank"
                  rel="noopener"
                  :data-testid="`dupxgid-link-${item.gid}`"
                >
                  {{ itemTitle(item) }}
                </a>
                <span class="xgid__meta">
                  <span class="xgid__badge">
                    {{
                      isLocal(item)
                        ? t("maintenance.duplicates.library.current")
                        : t("maintenance.duplicates.favorites.filterCloud")
                    }}
                  </span>
                  <span class="xgid__badge">#{{ item.gid }}</span>
                  <span v-if="item.category" class="xgid__badge">{{ item.category }}</span>
                  <span v-if="item.page_count || item.pages" class="xgid__badge">
                    {{ item.page_count ?? item.pages }} P
                  </span>
                  <span v-if="item.file_size" class="xgid__badge">
                    {{ formatBytes(item.file_size) }}
                  </span>
                  <span v-if="item.storage_type" class="xgid__badge">
                    {{ item.storage_type }}
                  </span>
                </span>
              </span>
            </label>
          </div>
        </div>
      </article>

      <PagerBar
        v-if="groups.length > PAGE_SIZE"
        :page="page"
        :pages="totalPages"
        :total="groups.length"
        testid="dupxgid-pager"
        @change="goPage"
      />
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
      testid="dupxgid-confirm"
      @confirm="confirmRemove"
      @cancel="confirmOpen = false"
    />
  </section>
</template>

<style scoped>
.xgid {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.xgid__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.xgid__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.xgid__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.xgid__subtitle,
.xgid__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.xgid__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.xgid__link {
  margin-left: auto;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.xgid__danger {
  border-color: var(--gv-color-error);
  color: var(--gv-color-error);
}

.xgid__info {
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.xgid__info summary {
  cursor: pointer;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
}

.xgid__info p {
  margin: var(--gv-space-2) 0 0;
}

.xgid__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.xgid__group {
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.xgid__group--ignored {
  opacity: 0.72;
}

.xgid__group-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.xgid__count {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.xgid__group-title {
  min-width: 0;
  overflow: hidden;
  flex: 1;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xgid__artist {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.xgid__group-actions {
  display: flex;
  gap: var(--gv-space-2);
}

.xgid__row {
  padding-top: var(--gv-space-3);
}

.xgid__check {
  display: flex;
  align-items: flex-start;
  gap: var(--gv-space-3);
}

.xgid__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.xgid__item-title {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xgid__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.xgid__badge {
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
  .xgid__link {
    margin-left: 0;
  }
}
</style>
