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
const openCount = computed(() => groups.value.filter((group) => group.status === "open").length);
const emptyLabel = computed(() =>
  filter.value === "open"
    ? t("maintenance.duplicates.library.noneOpen")
    : filter.value === "dismissed"
      ? t("maintenance.duplicates.library.noneDismissed")
      : t("maintenance.duplicates.library.empty"),
);

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

function statusLabel(group: LibraryDuplicateGroup): string {
  return group.status === "dismissed"
    ? t("maintenance.duplicates.library.statusDismissed")
    : t("maintenance.duplicates.library.statusOpen");
}

function setFilter(next: Filter): void {
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
    <header class="dup__header">
      <p class="dup__eyebrow">{{ t("maintenance.duplicates.library.eyebrow") }}</p>
      <h1 class="dup__title">{{ t("maintenance.duplicates.library.title") }}</h1>
      <p class="dup__subtitle">{{ t("maintenance.duplicates.library.subtitle") }}</p>
    </header>

    <MaintenanceTabs active="duplicates" />

    <div class="dup__toolbar">
      <Button data-testid="duplicates-scan" :loading="scanning" @click="scan">
        {{ scanning ? t("maintenance.duplicates.library.scanning") : t("maintenance.duplicates.library.scan") }}
      </Button>
      <Button variant="outlined" data-testid="duplicates-refresh" @click="load">
        {{ t("maintenance.duplicates.library.refresh") }}
      </Button>
      <Button
        v-for="item in FILTERS"
        :key="item"
        size="compact"
        :variant="filter === item ? 'tonal' : 'outlined'"
        :data-testid="`duplicates-filter-${item}`"
        @click="setFilter(item)"
      >
        {{
          item === "all"
            ? t("maintenance.duplicates.library.filterAll")
            : item === "open"
              ? t("maintenance.duplicates.library.filterOpen")
              : t("maintenance.duplicates.library.filterDismissed")
        }}
      </Button>
    </div>

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
      :title="emptyLabel"
      testid="duplicates-empty"
    />

    <template v-else>
      <p class="dup__summary" data-testid="duplicates-summary">
        {{
          t("maintenance.duplicates.library.found", {
            groups: filtered.length,
            items: filtered.reduce((sum, group) => sum + group.copies.length, 0),
          })
        }}
        <span v-if="openCount"> · {{ openCount }} {{ t("maintenance.duplicates.library.filterOpen") }}</span>
      </p>

      <article
        v-for="group in pageGroups"
        :key="group.gid"
        class="dup__group"
        :data-testid="`duplicates-group-${group.gid}`"
      >
        <header class="dup__group-head">
          <span class="dup__count">#{{ group.gid }}</span>
          <span class="dup__group-title">{{ groupTitle(group) }}</span>
          <span v-if="group.policy" class="dup__badge">{{ group.policy }}</span>
          <span class="dup__badge">{{ statusLabel(group) }}</span>
          <span class="dup__group-actions">
            <Button
              variant="outlined"
              size="compact"
              :data-testid="`duplicates-dismiss-${group.gid}`"
              @click="setStatus(group, group.status === 'open' ? 'dismissed' : 'open')"
            >
              {{
                group.status === "open"
                  ? t("maintenance.duplicates.library.dismiss")
                  : t("maintenance.duplicates.library.restore")
              }}
            </Button>
          </span>
        </header>

        <div
          v-for="copy in group.copies"
          :key="copy.key"
          class="dup__row"
          :data-testid="`duplicates-copy-${copy.key}`"
        >
          <GalleryThumb :src="copyThumb(copy)" :alt="copyTitle(copy)" />
          <div class="dup__body">
            <component
              :is="copy.gallery_id != null ? RouterLink : 'span'"
              class="dup__copy-title"
              :to="copy.gallery_id != null ? { name: 'gallery', params: { id: copy.gallery_id } } : undefined"
            >
              {{ copyTitle(copy) }}
            </component>
            <div class="dup__meta">
              <span class="dup__badge">
                {{
                  copy.gallery_id != null
                    ? t("maintenance.duplicates.library.current")
                    : copy.storage_type || "—"
                }}
              </span>
              <span v-if="copy.page_count" class="dup__badge">
                {{ t("maintenance.duplicates.library.pages", { n: copy.page_count }) }}
              </span>
              <span v-if="copySize(copy)" class="dup__badge">{{ copySize(copy) }}</span>
              <span v-if="copy.posted_at" class="dup__badge">
                {{ formatDate(copy.posted_at) }}
              </span>
            </div>
            <div v-if="copy.tags?.length" class="dup__tags">
              <span
                v-for="tag in copy.tags"
                :key="`${tag.namespace}:${tag.name}`"
                class="dup__tag"
              >
                {{ tag.display || tag.name }}
              </span>
            </div>
            <div class="dup__copy-actions">
              <Button
                variant="outlined"
                size="compact"
                :data-testid="`duplicates-keep-${copy.key}`"
                @click="askKeep(copy, group, false)"
              >
                {{ t("maintenance.duplicates.library.keep") }}
              </Button>
              <Button
                variant="outlined"
                size="compact"
                class="dup__danger"
                :data-testid="`duplicates-keep-delete-${copy.key}`"
                @click="askKeep(copy, group, true)"
              >
                {{ t("maintenance.duplicates.library.keepDelete") }}
              </Button>
            </div>
          </div>
        </div>
      </article>

      <PagerBar
        v-if="filtered.length > PAGE_SIZE"
        :page="page"
        :pages="totalPages"
        :total="filtered.length"
        testid="duplicates-pager"
        @change="goPage"
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

.dup__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.dup__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.dup__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.dup__subtitle,
.dup__summary {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.dup__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.dup__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.dup__group {
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.dup__group-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.dup__count {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.dup__group-title {
  min-width: 0;
  overflow: hidden;
  flex: 1;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dup__group-actions {
  display: flex;
  gap: var(--gv-space-2);
}

.dup__row {
  display: flex;
  gap: var(--gv-space-3);
  padding-top: var(--gv-space-3);
}

.dup__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.dup__copy-title {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dup__meta,
.dup__tags,
.dup__copy-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.dup__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.dup__tag {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.dup__danger {
  border-color: var(--gv-color-error);
  color: var(--gv-color-error);
}

@media (max-width: 599px) {
  .dup__row {
    flex-direction: column;
  }
}
</style>
