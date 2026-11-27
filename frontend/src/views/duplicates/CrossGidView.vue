<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import IconButton from "@/components/ui/IconButton.vue";
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
  dismissCrossGidDuplicate,
  fetchCrossGidDuplicates,
  refreshCrossGidDuplicates,
  removeFavorites,
  restoreCrossGidDuplicate,
  type CrossGidGroup,
  type CrossGidItem,
  type CrossGidResponse,
} from "@/api/duplicates";
import { useUiStore } from "@/stores/ui";
import { formatBytes } from "@/stores/library";
import { galleryThumbUrl } from "@/views/updates/url";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const { t, te } = useI18n();

type Filter = "all" | "local" | "cloud";
type RemoveMode = "unfav" | "delete";
type ListStatus = "open" | "dismissed";
const FILTERS: readonly Filter[] = ["all", "local", "cloud"];
const STATUSES: readonly ListStatus[] = ["open", "dismissed"];
const PAGE_SIZE = 24;
const STORAGE_KEYS = ["folder", "ehviewer_dir", "jhentai_dir", "cbz", "cbr", "pdf", "7z"] as const;

const response = ref<CrossGidResponse | null>(null);
const loading = ref(true);
const error = ref("");
const busy = ref(false);
const selected = ref<number[]>([]);
const listStatus = ref<ListStatus>("open");
const collapsed = ref<string[]>([]);
const confirmOpen = ref(false);
const removeMode = ref<RemoveMode>("unfav");
const infoOpen = ref(false);
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
const statusOptions = computed<SegmentedOption[]>(() =>
  STATUSES.map((item) => ({
    value: item,
    label:
      item === "open"
        ? t("maintenance.duplicates.cross.statusOpen")
        : t("maintenance.duplicates.cross.statusDismissed"),
  })),
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

function itemTo(item: CrossGidItem) {
  return isLocal(item) ? { name: "gallery", params: { id: item.gallery_id } } : null;
}

function storageLabel(storage: string | null | undefined): string {
  if (!storage || !STORAGE_KEYS.includes(storage as (typeof STORAGE_KEYS)[number])) return "";
  return t(`maintenance.duplicates.storage.${storage}`);
}

function categoryLabel(category: string | null | undefined): string {
  const value = (category ?? "").trim();
  if (!value) return "";
  const key = `gallery.categories.${value}`;
  return te(key) ? t(key) : "";
}

function isIgnored(group: CrossGidGroup): boolean {
  return listStatus.value === "dismissed" && group.status !== "open";
}

function groupTestId(group: CrossGidGroup, verb: "dismiss" | "restore"): string {
  return `dupxgid-${verb}-${group.id ?? group.key}`;
}

function isCollapsed(group: CrossGidGroup): boolean {
  return collapsed.value.includes(group.key);
}

function toggleCollapsed(group: CrossGidGroup): void {
  collapsed.value = isCollapsed(group)
    ? collapsed.value.filter((key) => key !== group.key)
    : [...collapsed.value, group.key];
}

function setFilter(next: string): void {
  if (!FILTERS.includes(next as Filter)) return;
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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function signature(data: CrossGidResponse | null): string {
  return JSON.stringify(
    (data?.groups ?? []).map((group) => [group.key, group.status ?? "", group.items.length]),
  );
}

async function load(): Promise<void> {
  const token = ++seq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchCrossGidDuplicates(listStatus.value);
    if (token !== seq) return;
    applyResponse(data);
  } catch (cause) {
    if (token !== seq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (token === seq) loading.value = false;
  }
}

function setListStatus(next: string): void {
  if (!STATUSES.includes(next as ListStatus) || next === listStatus.value) return;
  listStatus.value = next as ListStatus;
  selected.value = [];
  void load();
}

async function recompute(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  const before = signature(response.value);
  try {
    await refreshCrossGidDuplicates();
    // T5.2 moved the scan off the request path: the POST answers 202 with the
    // current view. Read the persisted result until the scan lands.
    for (let index = 0; index < 6; index += 1) {
      await delay(900);
      await load();
      if (signature(response.value) !== before) break;
    }
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

function removeGroup(key: string): void {
  if (!response.value) return;
  const groups = response.value.groups.filter((group) => group.key !== key);
  response.value = { ...response.value, groups, count: groups.length };
}

async function dismissGroup(group: CrossGidGroup): Promise<boolean> {
  if (group.id == null) {
    ui.error(t("maintenance.duplicates.cross.missingId"));
    return false;
  }
  try {
    await dismissCrossGidDuplicate(group.id);
    removeGroup(group.key);
    return true;
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
    return false;
  }
}

async function restoreGroup(group: CrossGidGroup): Promise<void> {
  if (group.id == null) {
    ui.error(t("maintenance.duplicates.cross.missingId"));
    return;
  }
  try {
    await restoreCrossGidDuplicate(group.id);
    removeGroup(group.key);
    ui.success(t("maintenance.duplicates.cross.restoredOk"));
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function dismissSelected(): Promise<void> {
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
    if (await dismissGroup(group)) ok += 1;
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
    <PageHeader
      :title="t('maintenance.duplicates.cross.title')"
      :count="itemCount"
      :count-label="summary"
      :subtitle="t('maintenance.duplicates.cross.subtitle')"
      testid="dupxgid-header"
    />

    <MaintenanceNav />

    <Toolbar class="xgid__actions" testid="dupxgid-toolbar">
      <ToolbarGroup end>
        <Button icon="duplicates" :loading="busy" data-testid="dupxgid-recompute" @click="recompute">
          {{ t("maintenance.duplicates.cross.recompute") }}
        </Button>
        <Button variant="outlined" icon="retry" data-testid="dupxgid-refresh" @click="load">
          {{ t("maintenance.duplicates.cross.refresh") }}
        </Button>
      </ToolbarGroup>
    </Toolbar>

    <Toolbar class="xgid__filters" size="sm" testid="dupxgid-statusbar">
      <ToolbarGroup>
        <SegmentedControl
          :model-value="listStatus"
          :options="statusOptions"
          :label="t('maintenance.duplicates.cross.statusLabel')"
          testid="dupxgid-status"
          @update:model-value="setListStatus"
        />
      </ToolbarGroup>
    </Toolbar>

    <Toolbar class="xgid__filters" size="sm" testid="dupxgid-filters">
      <ToolbarGroup>
        <SegmentedControl
          :model-value="filter"
          :options="filterOptions"
          :label="t('maintenance.duplicates.favorites.filterAll')"
          testid="dupxgid-filter"
          @update:model-value="setFilter"
        />
      </ToolbarGroup>
    </Toolbar>

    <p class="xgid__summary" data-testid="dupxgid-summary">{{ summary }}</p>

    <SelectionBar
      v-if="listStatus === 'open'"
      :count="selectedCount"
      :label="t('maintenance.shared.selected', { n: selectedCount })"
      testid="dupxgid-selection"
      @clear="clearSelection"
    >
      <Button variant="outlined" data-testid="dupxgid-ignore" @click="dismissSelected">
        {{ t("maintenance.duplicates.cross.dismissSelected") }}
      </Button>
      <template #danger>
        <Button
          variant="outlined"
          danger
          :disabled="!favoritedSelected.length"
          data-testid="dupxgid-unfav"
          @click="openRemove('unfav')"
        >
          {{ t("maintenance.duplicates.favorites.unfav") }} ({{ selectedCount }})
        </Button>
        <Button
          variant="outlined"
          danger
          :disabled="!favoritedSelected.length"
          data-testid="dupxgid-unfav-delete"
          @click="openRemove('delete')"
        >
          {{ t("maintenance.duplicates.favorites.unfavDelete") }}
        </Button>
      </template>
    </SelectionBar>

    <section class="xgid__info" :aria-label="t('maintenance.duplicates.cross.infoSummary')">
      <Button
        variant="text"
        :icon="infoOpen ? 'chevron-up' : 'chevron-down'"
        :aria-expanded="infoOpen"
        data-testid="dupxgid-info-toggle"
        @click="infoOpen = !infoOpen"
      >
        {{ t("maintenance.duplicates.cross.infoSummary") }}
      </Button>
      <p v-if="infoOpen" class="xgid__info-body">
        {{ t("maintenance.duplicates.cross.infoDetail") }}
      </p>
    </section>

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
      icon="duplicates"
      :title="t('maintenance.duplicates.cross.hintTitle')"
      :body="t('maintenance.duplicates.cross.hintBody')"
      :action-label="t('maintenance.duplicates.cross.recompute')"
      testid="dupxgid-hint"
      @action="recompute"
    />

    <EmptyState
      v-else-if="!groups.length"
      icon="duplicates"
      :title="
        listStatus === 'dismissed'
          ? t('maintenance.duplicates.cross.noneDismissed')
          : t('maintenance.duplicates.cross.none')
      "
      :body="
        listStatus === 'dismissed'
          ? t('maintenance.duplicates.cross.noneDismissedBody')
          : t('maintenance.duplicates.cross.noneBody')
      "
      :action-label="t('maintenance.duplicates.cross.recompute')"
      testid="dupxgid-empty"
      @action="recompute"
    />

    <template v-else>
      <DuplicateGroupCard
        v-for="group in pageGroups"
        :key="group.key"
        :title="groupTitle(group)"
        :muted="isIgnored(group)"
        :testid="`dupxgid-group-${group.key}`"
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
            v-if="listStatus === 'open'"
            variant="outlined"
            size="sm"
            data-testid="dupxgid-select-group"
            @click="toggleGroup(group)"
          >
            {{ t("maintenance.shared.select") }}
          </Button>
          <Button
            v-if="listStatus === 'open'"
            variant="outlined"
            size="sm"
            :data-testid="groupTestId(group, 'dismiss')"
            @click="dismissGroup(group)"
          >
            {{ t("maintenance.duplicates.cross.dismiss") }}
          </Button>
          <Button
            v-else
            variant="outlined"
            size="sm"
            icon="retry"
            :data-testid="groupTestId(group, 'restore')"
            @click="restoreGroup(group)"
          >
            {{ t("maintenance.duplicates.cross.restore") }}
          </Button>
          <IconButton
            size="sm"
            :name="isCollapsed(group) ? 'chevron-down' : 'chevron-up'"
            :label="
              isCollapsed(group)
                ? t('maintenance.duplicates.cross.expandGroup')
                : t('maintenance.duplicates.cross.collapseGroup')
            "
            :aria-expanded="!isCollapsed(group)"
            data-testid="dupxgid-collapse"
            @click="toggleCollapsed(group)"
          />
        </template>

        <div v-show="!isCollapsed(group)">
          <DuplicateCopyRow
            v-for="item in group.items"
            :key="item.gid"
            :title="itemTitle(item)"
            :thumb="itemThumb(item)"
            :to="itemTo(item)"
            :href="isLocal(item) ? null : item.url"
            :link-testid="isLocal(item) ? undefined : `dupxgid-link-${item.gid}`"
            :testid="`dupxgid-item-${item.gid}`"
          >
            <template #leading>
              <Checkbox
                v-if="listStatus === 'open'"
                :model-value="selected.includes(item.gid)"
                :aria-label="t('maintenance.shared.select')"
                :data-testid="`dupxgid-select-${item.gid}`"
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
              <DuplicateBadge>#{{ item.gid }}</DuplicateBadge>
              <DuplicateBadge v-if="categoryLabel(item.category)">
                {{ categoryLabel(item.category) }}
              </DuplicateBadge>
              <DuplicateBadge v-if="item.page_count ?? item.pages">
                {{ t("maintenance.duplicates.library.pages", { n: item.page_count ?? item.pages }) }}
              </DuplicateBadge>
              <DuplicateBadge v-if="item.file_size">{{ formatBytes(item.file_size) }}</DuplicateBadge>
              <DuplicateBadge v-if="storageLabel(item.storage_type)">
                {{ storageLabel(item.storage_type) }}
              </DuplicateBadge>
            </template>
          </DuplicateCopyRow>
        </div>
      </DuplicateGroupCard>

      <Pager
        v-if="groups.length > PAGE_SIZE"
        :page="page"
        :total-pages="totalPages"
        testid="dupxgid-pager"
        @update:page="goPage"
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

.xgid__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.xgid__filters {
  flex-wrap: nowrap;
}

.xgid__filters :deep(.segmented) {
  min-width: max-content;
}

.xgid__info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--gv-space-1);
}

.xgid__info-body {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.xgid__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}
</style>
