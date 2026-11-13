<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl, { type SegmentedOption } from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import DuplicateBadge from "./components/DuplicateBadge.vue";
import DuplicateCopyRow from "./components/DuplicateCopyRow.vue";
import DuplicateGroupCard from "./components/DuplicateGroupCard.vue";
import MaintenanceNav from "./components/MaintenanceNav.vue";
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
import { galleryThumbUrl } from "@/views/updates/url";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
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
const page = computed(() => {
  const parsed = Number.parseInt(first(route.query.page), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
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
const totalPages = computed(() => Math.max(1, Math.ceil(groups.value.length / PAGE_SIZE)));
const pageGroups = computed(() =>
  groups.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
);
const itemCount = computed(() =>
  groups.value.reduce((sum, group) => sum + group.items.length, 0),
);
const summary = computed(() =>
  t("maintenance.duplicates.favorites.found", {
    groups: groups.value.length,
    items: itemCount.value,
  }),
);
const filterOptions = computed<SegmentedOption[]>(() =>
  FILTERS.map((item) => ({
    value: item,
    label:
      item === "all"
        ? t("maintenance.duplicates.favorites.filterAll")
        : item === "local"
          ? t("maintenance.duplicates.favorites.filterLocal")
          : t("maintenance.duplicates.favorites.filterCloud"),
  })),
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

function itemTo(item: FavoriteDuplicateItem) {
  return isLocal(item) ? { name: "gallery", params: { id: item.gallery_id } } : null;
}

function isIgnored(group: FavoriteDuplicateGroup): boolean {
  return locallyIgnored.value.includes(group.key);
}

function setFilter(next: string): void {
  if (!FILTERS.includes(next as Filter)) return;
  void router.push({
    name: "favorites-manage",
    query: { ...(next === "all" ? {} : { filter: next }) },
  });
}

function goPage(next: number): void {
  void router.push({
    name: "favorites-manage",
    query: {
      ...(filter.value === "all" ? {} : { filter: filter.value }),
      ...(next > 1 ? { page: next } : {}),
    },
  });
}

function openIgnored(): void {
  void router.push({ name: "favorites-ignored" });
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
    <PageHeader
      :title="t('maintenance.duplicates.favorites.title')"
      :count="itemCount"
      :count-label="summary"
      :subtitle="t('maintenance.duplicates.favorites.subtitle')"
      testid="dupfav-header"
    >
      <template #actions>
        <Button variant="text" icon="favorite-outline" data-testid="dupfav-ignored-link" @click="openIgnored">
          {{ t("maintenance.duplicates.favorites.ignoredPageLink") }}
        </Button>
      </template>
    </PageHeader>

    <MaintenanceNav />

    <Toolbar class="favdup__actions" testid="dupfav-toolbar">
      <ToolbarGroup end>
        <Button icon="favorites" :loading="scanning" data-testid="dupfav-scan" @click="scan">
          {{
            scanning
              ? t("maintenance.duplicates.favorites.scanning")
              : t("maintenance.duplicates.favorites.scan")
          }}
        </Button>
      </ToolbarGroup>
    </Toolbar>

    <Toolbar class="favdup__filters" size="sm" testid="dupfav-filters">
      <ToolbarGroup>
        <SegmentedControl
          :model-value="filter"
          :options="filterOptions"
          :label="t('maintenance.duplicates.favorites.filterAll')"
          testid="dupfav-filter"
          @update:model-value="setFilter"
        />
      </ToolbarGroup>
    </Toolbar>

    <p class="favdup__summary" data-testid="dupfav-summary">{{ summary }}</p>

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

    <SelectionBar
      :count="selectedCount"
      :label="t('maintenance.shared.selected', { n: selectedCount })"
      testid="dupfav-selection"
      @clear="clearSelection"
    >
      <Button variant="outlined" data-testid="dupfav-ignore" @click="ignoreSelected">
        {{ t("maintenance.duplicates.favorites.ignoreSelected") }}
      </Button>
      <template #danger>
        <Button variant="outlined" danger data-testid="dupfav-unfav" @click="openRemove('unfav')">
          {{ t("maintenance.duplicates.favorites.unfav") }} ({{ selectedCount }})
        </Button>
        <Button
          variant="outlined"
          danger
          data-testid="dupfav-unfav-delete"
          @click="openRemove('delete')"
        >
          {{ t("maintenance.duplicates.favorites.unfavDelete") }}
        </Button>
      </template>
    </SelectionBar>

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
        icon="favorites"
        :title="status ? t('maintenance.duplicates.favorites.empty') : t('maintenance.duplicates.favorites.hint')"
        :body="t('maintenance.duplicates.favorites.emptyBody')"
        :action-label="t('maintenance.duplicates.favorites.scan')"
        testid="dupfav-empty"
        @action="scan"
      />

      <template v-else>
        <DuplicateGroupCard
          v-for="group in pageGroups"
          :key="group.key"
          :title="groupTitle(group)"
          :muted="isIgnored(group)"
          :testid="`dupfav-group-${group.key}`"
        >
          <template #badges>
            <DuplicateBadge size="sm" tone="primary">{{ group.items.length }}</DuplicateBadge>
            <DuplicateBadge v-if="group.artist" size="sm">{{ group.artist }}</DuplicateBadge>
            <DuplicateBadge v-if="isIgnored(group)" size="sm" tone="warning">
              {{ t("maintenance.duplicates.favorites.ignored") }}
            </DuplicateBadge>
          </template>
          <template #actions>
            <Button
              variant="outlined"
              size="sm"
              data-testid="dupfav-select-group"
              @click="toggleGroup(group)"
            >
              {{ t("maintenance.shared.select") }}
            </Button>
          </template>

          <DuplicateCopyRow
            v-for="item in group.items"
            :key="item.gid"
            :title="itemTitle(item)"
            :thumb="itemThumb(item)"
            :to="itemTo(item)"
            :href="isLocal(item) ? null : item.url"
            :tags="item.tags ?? []"
            :testid="`dupfav-item-${item.gid}`"
          >
            <template #leading>
              <Checkbox
                :model-value="selected.includes(item.gid)"
                :aria-label="t('maintenance.shared.select')"
                :data-testid="`dupfav-select-${item.gid}`"
                @change="toggle(item.gid)"
              />
            </template>
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

        <Pager
          v-if="groups.length > PAGE_SIZE"
          :page="page"
          :total-pages="totalPages"
          testid="dupfav-pager"
          @update:page="goPage"
        />
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

.favdup__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.favdup__filters {
  flex-wrap: nowrap;
}

.favdup__filters :deep(.segmented) {
  min-width: max-content;
}

.favdup__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
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
</style>
