<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl, { type SegmentedOption } from "@/components/ui/SegmentedControl.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import DuplicateBadge from "./components/DuplicateBadge.vue";
import DuplicateCopyRow from "./components/DuplicateCopyRow.vue";
import DuplicateGroupCard from "./components/DuplicateGroupCard.vue";
import MaintenanceNav from "./components/MaintenanceNav.vue";
import {
  duplicateThumbPath,
  fetchLibraryDuplicates,
  fetchLibraryScanStatus,
  resolveLibraryDuplicate,
  setLibraryDuplicateStatus,
  startLibraryScan,
  type LibraryDuplicateCopy,
  type LibraryDuplicateGroup,
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

type Filter = "all" | "open" | "dismissed";
const FILTERS: readonly Filter[] = ["all", "open", "dismissed"];
const PAGE_SIZE = 24;

const groups = ref<LibraryDuplicateGroup[]>([]);
const loading = ref(true);
const error = ref("");
const scanning = ref(false);
const confirmOpen = ref(false);
const pending = ref<{ gid: number; path: string; deleteOthers: boolean; title: string } | null>(
  null,
);
let seq = 0;

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

const filter = computed<Filter>(() => {
  const value = first(route.query.filter);
  return value === "open" || value === "dismissed" ? value : "all";
});
const page = computed(() => {
  const parsed = Number.parseInt(first(route.query.page), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
});
const filtered = computed(() =>
  filter.value === "all"
    ? groups.value
    : groups.value.filter((group) => group.status === filter.value),
);
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / PAGE_SIZE)));
const pageGroups = computed(() =>
  filtered.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
);
const itemCount = computed(() =>
  filtered.value.reduce((sum, group) => sum + group.copies.length, 0),
);
const openCount = computed(() => groups.value.filter((group) => group.status === "open").length);
const summary = computed(() =>
  t("maintenance.duplicates.library.found", {
    groups: filtered.value.length,
    items: itemCount.value,
  }),
);
const filterOptions = computed<SegmentedOption[]>(() =>
  FILTERS.map((item) => ({
    value: item,
    label:
      item === "all"
        ? t("maintenance.duplicates.library.filterAll")
        : item === "open"
          ? t("maintenance.duplicates.library.filterOpen")
          : t("maintenance.duplicates.library.filterDismissed"),
  })),
);
const emptyTitle = computed(() =>
  filter.value === "open"
    ? t("maintenance.duplicates.library.noneOpen")
    : filter.value === "dismissed"
      ? t("maintenance.duplicates.library.noneDismissed")
      : t("maintenance.duplicates.library.empty"),
);
const emptyAction = computed(() =>
  filter.value === "all"
    ? t("maintenance.duplicates.library.scan")
    : t("maintenance.duplicates.library.showAll"),
);
const POLICY_KEYS = [
  "keep_first",
  "prefer_more_pages",
  "prefer_newer",
  "prefer_larger",
  "prefer_smaller",
  "manual",
] as const;
const STORAGE_KEYS = ["folder", "ehviewer_dir", "jhentai_dir", "cbz", "cbr", "pdf", "7z"] as const;

function groupTitle(group: LibraryDuplicateGroup): string {
  const copy = group.copies[0];
  return copy?.display_title || copy?.title || `gid ${group.gid}`;
}

function copyTitle(copy: LibraryDuplicateCopy): string {
  return copy.display_title || copy.title || copy.path;
}

function copyThumb(copy: LibraryDuplicateCopy): string {
  return copy.gallery_id != null
    ? galleryThumbUrl(copy.gallery_id)
    : duplicateThumbPath(copy.key);
}

function copySize(copy: LibraryDuplicateCopy): string {
  return formatBytes(copy.file_size);
}

function policyLabel(policy: string | null | undefined): string {
  if (!policy || !POLICY_KEYS.includes(policy as (typeof POLICY_KEYS)[number])) return "";
  return t(`maintenance.duplicates.library.policy.${policy}`);
}

function storageLabel(storage: string | null | undefined): string {
  if (!storage || !STORAGE_KEYS.includes(storage as (typeof STORAGE_KEYS)[number])) return "";
  return t(`maintenance.duplicates.storage.${storage}`);
}

function copyOrigin(copy: LibraryDuplicateCopy): string {
  return copy.gallery_id != null
    ? t("maintenance.duplicates.library.current")
    : storageLabel(copy.storage_type);
}

function statusLabel(group: LibraryDuplicateGroup): string {
  return group.status === "dismissed"
    ? t("maintenance.duplicates.library.statusDismissed")
    : t("maintenance.duplicates.library.statusOpen");
}

function setFilter(next: string): void {
  if (!FILTERS.includes(next as Filter)) return;
  void router.push({
    name: "duplicates",
    query: next === "all" ? {} : { filter: next },
  });
}

function goPage(next: number): void {
  void router.push({
    name: "duplicates",
    query: { ...(filter.value === "all" ? {} : { filter: filter.value }), page: next },
  });
}

async function load(): Promise<void> {
  const token = ++seq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchLibraryDuplicates();
    if (token !== seq) return;
    groups.value = data.groups ?? [];
  } catch (cause) {
    if (token !== seq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (token === seq) loading.value = false;
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function scan(): Promise<void> {
  if (scanning.value) return;
  scanning.value = true;
  try {
    const result = await startLibraryScan();
    if (result.status !== "paused") {
      for (let index = 0; index < 120; index += 1) {
        await delay(1000);
        const state = await fetchLibraryScanStatus();
        if (!state.running) break;
      }
    }
    ui.success(t("maintenance.updates.message.scanStarted"));
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    scanning.value = false;
  }
}

function askKeep(copy: LibraryDuplicateCopy, group: LibraryDuplicateGroup, deleteOthers: boolean): void {
  pending.value = {
    gid: group.gid,
    path: copy.path,
    deleteOthers,
    title: copyTitle(copy),
  };
  confirmOpen.value = true;
}

async function confirmKeep(): Promise<void> {
  const target = pending.value;
  if (!target) return;
  confirmOpen.value = false;
  try {
    const result = await resolveLibraryDuplicate(target.gid, target.path, target.deleteOthers);
    groups.value = result.groups ?? [];
    if (result.failed_paths?.length) {
      ui.error(
        t("maintenance.duplicates.favorites.deleteFail", { n: result.failed_paths.length }),
      );
    } else {
      ui.success(
        target.deleteOthers
          ? t("maintenance.duplicates.library.deletedOthers")
          : t("maintenance.duplicates.library.kept"),
      );
    }
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  } finally {
    pending.value = null;
  }
}

async function setStatus(group: LibraryDuplicateGroup, status: "open" | "dismissed"): Promise<void> {
  try {
    await setLibraryDuplicateStatus(group.gid, status);
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

const confirmTitle = computed(() =>
  pending.value?.deleteOthers
    ? t("maintenance.duplicates.library.confirmDeleteTitle")
    : t("maintenance.duplicates.library.confirmKeepTitle"),
);
const confirmBody = computed(() => {
  const target = pending.value;
  if (!target) return "";
  return target.deleteOthers
    ? t("maintenance.duplicates.library.confirmDeleteBody", {
        title: target.title,
        n: Math.max(0, (groups.value.find((group) => group.gid === target.gid)?.copies.length ?? 1) - 1),
      })
    : t("maintenance.duplicates.library.confirmKeepBody", { title: target.title });
});

watch(
  () => [filter.value, page.value] as const,
  () => {
    void load();
  },
);

onMounted(load);
</script>

<template>
  <section class="dup" data-testid="duplicates-view">
    <PageHeader
      :title="t('maintenance.duplicates.library.title')"
      :count="filtered.length"
      :count-label="summary"
      :subtitle="t('maintenance.duplicates.library.subtitle')"
      testid="duplicates-header"
    />

    <MaintenanceNav />

    <Toolbar class="dup__actions" testid="duplicates-toolbar">
      <ToolbarGroup end>
        <Button
          icon="duplicates"
          :loading="scanning"
          data-testid="duplicates-scan"
          @click="scan"
        >
          {{ scanning ? t("maintenance.duplicates.library.scanning") : t("maintenance.duplicates.library.scan") }}
        </Button>
        <Button variant="outlined" icon="retry" data-testid="duplicates-refresh" @click="load">
          {{ t("maintenance.duplicates.library.refresh") }}
        </Button>
      </ToolbarGroup>
    </Toolbar>

    <Toolbar class="dup__filters" size="sm" testid="duplicates-filters">
      <ToolbarGroup>
        <SegmentedControl
          :model-value="filter"
          :options="filterOptions"
          :label="t('maintenance.duplicates.library.filterAll')"
          testid="duplicates-filter"
          @update:model-value="setFilter"
        />
      </ToolbarGroup>
    </Toolbar>

    <p class="dup__summary" data-testid="duplicates-summary">
      {{ summary }}
      <span v-if="openCount"> · {{ openCount }} {{ t("maintenance.duplicates.library.filterOpen") }}</span>
    </p>

    <div v-if="loading" class="dup__skeletons" aria-hidden="true">
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
      v-else-if="!filtered.length"
      icon="duplicates"
      :title="emptyTitle"
      :body="t('maintenance.duplicates.library.emptyBody')"
      :action-label="emptyAction"
      testid="duplicates-empty"
      @action="filter === 'all' ? scan() : setFilter('all')"
    />

    <template v-else>
      <DuplicateGroupCard
        v-for="group in pageGroups"
        :key="group.gid"
        :gid="group.gid"
        :title="groupTitle(group)"
        :testid="`duplicates-group-${group.gid}`"
      >
        <template #badges>
          <DuplicateBadge
            v-if="policyLabel(group.policy)"
            size="sm"
            tone="primary"
            icon="duplicates"
          >
            {{ policyLabel(group.policy) }}
          </DuplicateBadge>
          <DuplicateBadge size="sm" :tone="group.status === 'dismissed' ? 'warning' : 'neutral'">
            {{ statusLabel(group) }}
          </DuplicateBadge>
          <DuplicateBadge size="sm">{{ group.copies.length }}</DuplicateBadge>
        </template>
        <template #actions>
          <Button
            variant="outlined"
            size="sm"
            :data-testid="`duplicates-dismiss-${group.gid}`"
            @click="setStatus(group, group.status === 'open' ? 'dismissed' : 'open')"
          >
            {{
              group.status === "open"
                ? t("maintenance.duplicates.library.dismiss")
                : t("maintenance.duplicates.library.restore")
            }}
          </Button>
        </template>

        <DuplicateCopyRow
          v-for="copy in group.copies"
          :key="copy.key"
          :title="copyTitle(copy)"
          :thumb="copyThumb(copy)"
          :to="copy.gallery_id != null ? { name: 'gallery', params: { id: copy.gallery_id } } : null"
          :tags="copy.tags ?? []"
          :testid="`duplicates-copy-${copy.key}`"
        >
          <template #meta>
            <DuplicateBadge v-if="copyOrigin(copy)">{{ copyOrigin(copy) }}</DuplicateBadge>
            <DuplicateBadge v-if="copy.page_count">
              {{ t("maintenance.duplicates.library.pages", { n: copy.page_count }) }}
            </DuplicateBadge>
            <DuplicateBadge v-if="copySize(copy)">{{ copySize(copy) }}</DuplicateBadge>
            <DuplicateBadge v-if="copy.posted_at">{{ formatDate(copy.posted_at) }}</DuplicateBadge>
          </template>
          <template #actions>
            <Button
              variant="tonal"
              size="sm"
              :data-testid="`duplicates-keep-${copy.key}`"
              @click="askKeep(copy, group, false)"
            >
              {{ t("maintenance.duplicates.library.keep") }}
            </Button>
            <Button
              variant="outlined"
              size="sm"
              danger
              :data-testid="`duplicates-keep-delete-${copy.key}`"
              @click="askKeep(copy, group, true)"
            >
              {{ t("maintenance.duplicates.library.keepDelete") }}
            </Button>
          </template>
        </DuplicateCopyRow>
      </DuplicateGroupCard>

      <Pager
        v-if="filtered.length > PAGE_SIZE"
        :page="page"
        :total-pages="totalPages"
        testid="duplicates-pager"
        @update:page="goPage"
      />
    </template>

    <ConfirmDialog
      :open="confirmOpen"
      :title="confirmTitle"
      :body="confirmBody"
      :confirm-label="
        pending?.deleteOthers
          ? t('maintenance.duplicates.library.keepDelete')
          : t('maintenance.duplicates.library.keep')
      "
      :danger="pending?.deleteOthers"
      testid="duplicates-confirm"
      @confirm="confirmKeep"
      @cancel="confirmOpen = false; pending = null"
    />
  </section>
</template>

<style scoped>
.dup {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.dup__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.dup__filters {
  flex-wrap: nowrap;
}

.dup__filters :deep(.segmented) {
  min-width: max-content;
}

.dup__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}
</style>
