<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Icon from "@/components/icons/Icon.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Menu from "@/components/ui/Menu.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl, { type SegmentedOption } from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import TextArea from "@/components/ui/TextArea.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import { PAGE_SIZES, clampPageSize } from "@/stores/library";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
import {
  cancelDownload,
  clearSuccessfulDownloads,
  createDownloadsBatch,
  deleteDownloadTask,
  fetchDownloads,
  fetchPauseState,
  fetchQuota,
  retryAllDownloads,
  retryDownload,
  setPauseState,
  type DownloadQuality,
  type DownloadStatus,
  type DownloadTask,
  type QuotaInfo,
} from "@/api/downloads";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";
import { ensureDownloadsMessages } from "./messages";
import { startVisiblePolling, type VisiblePoller } from "./poll";
import {
  canOpenGallery,
  errorSummary,
  formatDuration,
  formatSpeed,
  parseDownloadLinks,
  taskPercent,
} from "./format";

ensureDownloadsMessages();
// The reused GalleryThumb names the empty state from the maintenance namespace.
ensureMaintenanceMessages();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();

const FILTERS: Array<DownloadStatus | "all"> = [
  "all",
  "pending",
  "downloading",
  "success",
  "failed",
  "cancelled",
];

const STATUSES: DownloadStatus[] = [
  "pending",
  "downloading",
  "success",
  "failed",
  "cancelled",
];

/** Status icon per task state (C13): a coloured glyph, never a bare word. */
const STATUS_ICONS: Record<
  string,
  "history" | "downloads" | "status-success" | "status-error" | "status-blocked"
> = {
  pending: "history",
  downloading: "downloads",
  success: "status-success",
  failed: "status-error",
  cancelled: "status-blocked",
};

const items = ref<DownloadTask[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(true);
const error = ref("");
const filter = ref<DownloadStatus | "all">("all");
const selected = ref<number[]>([]);
const paused = ref(false);
const pauseBusy = ref(false);
const quota = ref<QuotaInfo | null>(null);
const quotaError = ref("");
const urls = ref("");
const quality = ref<"" | DownloadQuality>("");
const adding = ref(false);
const addOpen = ref(true);
const statusCounts = ref<Record<string, number>>({});
const dialog = ref<"" | "delete" | "delete-selected" | "clear-success" | "retry-all" | "archive">("");
const pendingDelete = ref<number[]>([]);
const archiveQuality = ref<DownloadQuality>("resample");
let requestSeq = 0;
let poller: VisiblePoller | null = null;

const pageSize = computed(() => clampPageSize(settings.pageSize, 24));
const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / Math.max(1, pageSize.value))),
);
const pageSizeChoices = computed(() => [...PAGE_SIZES]);
const hasSelection = computed(() => selected.value.length > 0);
const allCurrentSelected = computed(
  () => items.value.length > 0 && items.value.every((item) => selected.value.includes(item.id)),
);
const statusOptions = computed<SegmentedOption[]>(() =>
  FILTERS.map((value) => {
    const label = value === "all" ? t("legacy.filterAll") : statusLabel(value);
    const count = statusCounts.value[value];
    return {
      value,
      label: typeof count === "number" ? `${label} ${count}` : label,
    };
  }),
);
const quotaText = computed(() => {
  if (!quota.value) return "—";
  return quota.value.gp !== null ? `${quota.value.gp} GP` : "—";
});
const quotaLimit = computed(() => quota.value?.image_limit ?? null);
const quotaNearLimit = computed(
  () =>
    Boolean(quotaLimit.value && quotaLimit.value.limit > 0) &&
    (quotaLimit.value?.current ?? 0) / (quotaLimit.value?.limit ?? 1) > 0.8,
);
const qualityOptions = computed(() => [
  { value: "", label: t("legacy.dlDefaultQuality") },
  { value: "resample", label: t("legacy.qualityResample") },
  { value: "original", label: t("legacy.qualityOriginal") },
]);
const archiveQualityOptions = computed(() => [
  { value: "resample", label: t("legacy.archiveTierResample") },
  { value: "original", label: t("legacy.archiveTierOriginal") },
]);

function first(value: unknown): string {
  if (Array.isArray(value)) return first(value[0]);
  return value === null || value === undefined ? "" : String(value);
}

function statusLabel(status: string): string {
  const key: Record<string, string> = {
    pending: "dlStatusPending",
    downloading: "dlStatusDownloading",
    success: "dlStatusSuccess",
    failed: "dlStatusFailed",
    cancelled: "dlStatusCancelled",
  };
  return t(`legacy.${key[status] ?? "dlStatusPending"}`);
}

function statusIcon(status: string) {
  return STATUS_ICONS[status] ?? "status-info";
}

function isArchiveTask(task: DownloadTask): boolean {
  return Boolean(task.mode && task.mode.includes("archive"));
}

function isLive(task: DownloadTask): boolean {
  return task.status === "pending" || task.status === "downloading";
}

function badgeText(task: DownloadTask): string {
  if (isArchiveTask(task) && task.archive_fallback) return t("legacy.dlBadgeArchiveFallback");
  const tier =
    task.quality === "original" ? t("legacy.archiveTierOriginal") : t("legacy.archiveTierResample");
  return `${isArchiveTask(task) ? t("legacy.dlBadgeArchive") : t("legacy.dlBadgePages")} · ${tier}`;
}

function statusText(task: DownloadTask): string {
  if (task.status === "success" && task.archive_status) {
    if (task.archive_status === "ok") return t("legacy.dlArchivedCold");
    if (task.archive_status === "pending") return t("legacy.dlArchivePending");
    if (task.archive_status === "fail") {
      const suffix = task.archive_error ? `: ${task.archive_error}` : "";
      return `${t("legacy.dlArchiveFail")}${suffix}`;
    }
  }
  return statusLabel(task.status);
}

function taskMeta(task: DownloadTask): string {
  const parts: string[] = [];
  if (task.total_pages) parts.push(`${task.current_page ?? 0}/${task.total_pages}`);
  if (task.retry_count) parts.push(t("downloads.progress.retryCount", { n: task.retry_count }));
  const summary = errorSummary(task.error_message);
  if (summary) {
    parts.push(`${t("legacy.error")}: ${summary === "gone" ? t("legacy.dlGone") : summary}`);
  }
  return parts.join(" · ");
}

function speedText(task: DownloadTask): string {
  if (task.status !== "downloading") return "";
  const parts: string[] = [];
  const speed = formatSpeed(task.speed);
  if (speed) parts.push(`${t("downloads.progress.speed")} ${speed}`);
  const eta = formatDuration(task.eta_seconds);
  if (eta) parts.push(`${t("downloads.progress.eta")} ${eta}`);
  if (progressOf(task) === null) parts.push(t("downloads.progress.enumerating"));
  return parts.join(" · ");
}

/** One-line meta as the list renders it; also the tooltip for clipped text. */
function metaText(task: DownloadTask): string {
  const percent = task.status === "downloading" ? progressOf(task) : null;
  return [statusText(task), taskMeta(task), percent !== null ? `${percent}%` : "", speedText(task)]
    .filter(Boolean)
    .join(" · ");
}

function progressOf(task: DownloadTask): number | null {
  return taskPercent(task.current_page, task.total_pages);
}

function openGallery(task: DownloadTask): void {
  if (!canOpenGallery(task) || task.gallery_id == null) return;
  void router.push({ name: "gallery", params: { id: task.gallery_id } });
}

function isSelected(id: number): boolean {
  return selected.value.includes(id);
}

function toggleSelected(id: number, checked: boolean): void {
  if (checked && !isSelected(id)) selected.value = [...selected.value, id];
  if (!checked) selected.value = selected.value.filter((value) => value !== id);
}

function selectAll(): void {
  if (allCurrentSelected.value) {
    const current = new Set(items.value.map((item) => item.id));
    selected.value = selected.value.filter((id) => !current.has(id));
    return;
  }
  const merged = new Set([...selected.value, ...items.value.map((item) => item.id)]);
  selected.value = [...merged];
}

function clearSelection(): void {
  selected.value = [];
}

function setFilter(value: DownloadStatus | "all"): void {
  if (filter.value === value) return;
  filter.value = value;
  selected.value = [];
  void router.push({
    name: "downloads",
    query: value === "all" ? {} : { filter: value },
  });
}

function onFilterChange(value: string): void {
  setFilter(value as DownloadStatus | "all");
}

function goPage(target: number): void {
  if (target === page.value) return;
  void router.push({ name: "downloads", query: { ...route.query, page: String(target) } });
}

function onPageSize(value: number): void {
  const next = clampPageSize(value, settings.pageSize);
  settings.setPageSize(next);
  void router.push({ name: "downloads", query: { ...route.query, page: "1" } });
}

function syncFromRoute(): void {
  const raw = first(route.query.filter) as DownloadStatus | "";
  filter.value = FILTERS.includes(raw as DownloadStatus) ? (raw as DownloadStatus) : "all";
  const parsedPage = Number.parseInt(first(route.query.page), 10);
  page.value = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
  void load();
}

async function load(): Promise<void> {
  const seq = ++requestSeq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchDownloads({
      page: page.value,
      page_size: pageSize.value,
      status: filter.value === "all" ? undefined : filter.value,
    });
    if (seq !== requestSeq) return;
    items.value = data.items;
    total.value = data.total;
    const alive = new Set(data.items.map((item) => item.id));
    selected.value = selected.value.filter((id) => alive.has(id));
    void loadCounts(seq);
  } catch (cause) {
    if (seq !== requestSeq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
    items.value = [];
    total.value = 0;
  } finally {
    if (seq === requestSeq) {
      loading.value = false;
      ensurePoller();
    }
  }
}

/**
 * Per-status counters for the segmented control: one `page_size=1` probe per
 * status on load and after a mutation, never on the 2s poll, so the refresh
 * cadence and the scheduler are untouched.
 */
async function loadCounts(seq = requestSeq): Promise<void> {
  try {
    const entries = await Promise.all(
      STATUSES.map(async (status) => {
        const data = await fetchDownloads({ page: 1, page_size: 1, status });
        return [status, data.total] as const;
      }),
    );
    if (seq !== requestSeq) return;
    const next: Record<string, number> = {};
    let sum = 0;
    for (const [status, count] of entries) {
      next[status] = count;
      sum += count;
    }
    next.all = sum;
    statusCounts.value = next;
  } catch {
    statusCounts.value = {};
  }
}

function ensurePoller(): void {
  if (poller) return;
  poller = startVisiblePolling(() => {
    void refreshSilently();
  }, 2000);
}

async function refreshSilently(): Promise<void> {
  const seq = requestSeq;
  try {
    const data = await fetchDownloads({
      page: page.value,
      page_size: pageSize.value,
      status: filter.value === "all" ? undefined : filter.value,
    });
    if (seq !== requestSeq) return;
    items.value = data.items;
    total.value = data.total;
    const alive = new Set(data.items.map((item) => item.id));
    selected.value = selected.value.filter((id) => alive.has(id));
  } catch {
    /* polling failures never stop the scheduler */
  }
}

async function loadQuota(): Promise<void> {
  try {
    quota.value = await fetchQuota();
    quotaError.value = "";
  } catch (cause) {
    quotaError.value = cause instanceof Error ? cause.message : t("downloads.quota.error");
  }
}

async function loadPause(): Promise<void> {
  try {
    paused.value = await fetchPauseState();
  } catch {
    /* keep the previous state */
  }
}

async function togglePause(): Promise<void> {
  if (pauseBusy.value) return;
  pauseBusy.value = true;
  try {
    paused.value = await setPauseState(!paused.value);
  } catch (cause) {
    ui.error(
      cause instanceof Error && cause.message
        ? cause.message
        : t("downloads.page.pauseFailed"),
    );
  } finally {
    pauseBusy.value = false;
  }
}

function actionError(cause: unknown): void {
  if (cause && typeof cause === "object" && "status" in cause && cause.status === 409) {
    ui.error(t("legacy.dlAlreadyActive"));
    return;
  }
  ui.error(cause instanceof Error ? cause.message : t("legacy.error"));
}

async function cancel(id: number): Promise<void> {
  try {
    await cancelDownload(id);
    ui.success(`#${id} ${t("legacy.dlStatusCancelled")}`);
    await refreshSilently();
    void loadCounts();
  } catch (cause) {
    actionError(cause);
  }
}

async function retry(id: number): Promise<void> {
  try {
    await retryDownload(id);
    ui.success(`#${id} ${t("legacy.dlQueued")}`);
    await refreshSilently();
    void loadCounts();
  } catch (cause) {
    actionError(cause);
  }
}

function openDelete(id: number): void {
  pendingDelete.value = [id];
  dialog.value = "delete";
}

function openDeleteSelected(): void {
  if (!hasSelection.value) {
    ui.info(t("legacy.deleteSel"));
    return;
  }
  pendingDelete.value = [...selected.value];
  dialog.value = "delete-selected";
}

async function confirmDelete(): Promise<void> {
  const ids = [...pendingDelete.value];
  let ok = 0;
  let fail = 0;
  for (const id of ids) {
    try {
      await deleteDownloadTask(id);
      ok += 1;
    } catch {
      fail += 1;
    }
  }
  dialog.value = "";
  pendingDelete.value = [];
  selected.value = selected.value.filter((id) => !ids.includes(id));
  const summary = `${ok} ${t("legacy.deleted")}${fail ? `, ${fail} ${t("legacy.dlStatusFailed")}` : ""}`;
  if (ok) ui.success(summary);
  else ui.error(summary);
  await load();
}

async function clearSuccess(): Promise<void> {
  if (dialog.value !== "clear-success") return;
  dialog.value = "";
  try {
    const deleted = await clearSuccessfulDownloads();
    ui.success(t("legacy.clearedSuccessDl", { count: deleted }));
    await load();
  } catch (cause) {
    actionError(cause);
  }
}

async function retryAll(): Promise<void> {
  if (dialog.value !== "retry-all") return;
  dialog.value = "";
  try {
    const count = await retryAllDownloads();
    ui.success(t("legacy.retryAllSuccess", { count }));
    await load();
  } catch (cause) {
    actionError(cause);
  }
}

async function retrySelected(): Promise<void> {
  if (!hasSelection.value) {
    ui.info(t("legacy.retrySelected"));
    return;
  }
  let ok = 0;
  let fail = 0;
  for (const id of [...selected.value]) {
    try {
      await retryDownload(id);
      ok += 1;
    } catch {
      fail += 1;
    }
  }
  const summary = `${ok} ${t("legacy.dlQueued")}${fail ? `, ${fail} ${t("legacy.dlStatusFailed")}` : ""}`;
  if (ok) ui.success(summary);
  else ui.error(summary);
  await refreshSilently();
  void loadCounts();
}

async function addDownloads(archive = false): Promise<void> {
  if (adding.value) return;
  const parsed = parseDownloadLinks(urls.value);
  if (!parsed.length) {
    ui.error(t("downloads.batch.empty"));
    return;
  }
  if (archive && dialog.value === "archive") {
    dialog.value = "";
  }
  adding.value = true;
  try {
    const result = await createDownloadsBatch({
      items: parsed,
      quality: archive ? archiveQuality.value : quality.value || undefined,
      mode: archive ? "archive" : undefined,
    });
    ui.success(
      t("downloads.batch.summary", {
        queued: result.queued,
        skipped: result.skipped,
        gone: result.gone,
        failed: result.failed,
      }),
    );
    urls.value = "";
    await load();
    await loadQuota();
  } catch (cause) {
    actionError(cause);
  } finally {
    adding.value = false;
  }
}

function openArchive(): void {
  if (!parseDownloadLinks(urls.value).length) {
    ui.error(t("downloads.batch.empty"));
    return;
  }
  archiveQuality.value = "resample";
  dialog.value = "archive";
}

watch(
  () => route.query,
  () => syncFromRoute(),
  { immediate: true, deep: true },
);

onMounted(() => {
  void loadPause();
  void loadQuota();
});

onBeforeUnmount(() => {
  requestSeq += 1;
  poller?.stop();
  poller = null;
});
</script>

<template>
  <section class="downloads" data-testid="downloads-view">
    <PageHeader
      :title="t('legacy.downloads')"
      :count="total"
      :subtitle="t('legacy.downloadsSub')"
      testid="downloads-header"
    >
      <template #actions>
        <div class="downloads__status" data-testid="downloads-status">
          <Button
            :variant="paused ? 'filled' : 'outlined'"
            :icon="paused ? 'play' : 'pause'"
            :loading="pauseBusy"
            :title="t('legacy.pauseHint')"
            data-testid="downloads-pause"
            @click="togglePause"
          >
            {{ paused ? t("legacy.resume") : t("legacy.pause") }}
          </Button>
          <span v-if="paused" class="downloads__paused" data-testid="downloads-paused-badge">
            <Icon name="pause" size="dense" aria-hidden="true" />
            <span>{{ t("legacy.paused") }}</span>
          </span>
          <span class="downloads__quota" data-testid="downloads-gp">
            {{ t("legacy.gpTitle") }}: {{ quotaText }}
            <template v-if="quota?.cached"> · {{ t("downloads.quota.cached") }}</template>
          </span>
          <span
            class="downloads__quota"
            :class="{ 'downloads__quota--warn': quotaNearLimit }"
            data-testid="downloads-quota"
          >
            <template v-if="quotaLimit">
              {{ t("legacy.imageLimitTitle") }}: {{ quotaLimit.current }}/{{ quotaLimit.limit }}
            </template>
            <template v-else-if="quotaError">{{ quotaError }}</template>
          </span>
        </div>
      </template>
    </PageHeader>

    <section class="downloads__add" :aria-label="t('legacy.dlAddTitle')">
      <div class="downloads__add-head">
        <h2 class="downloads__add-title">{{ t("legacy.dlAddTitle") }}</h2>
        <IconButton
          :label="addOpen ? t('downloads.page.collapse') : t('downloads.page.expand')"
          :name="addOpen ? 'collapse' : 'expand'"
          :aria-expanded="addOpen"
          data-testid="downloads-add-toggle"
          @click="addOpen = !addOpen"
        />
      </div>
      <p class="downloads__add-hint">{{ t("legacy.dlAddHint") }}</p>
      <form v-show="addOpen" class="downloads__add-form" @submit.prevent="addDownloads(false)">
        <TextArea
          v-model="urls"
          :rows="2"
          :aria-label="t('legacy.dlAddPlaceholder')"
          :placeholder="t('legacy.dlAddPlaceholder')"
          data-testid="downloads-urls"
        />
        <Toolbar class="downloads__add-actions" size="lg" testid="downloads-add-actions">
          <ToolbarGroup class="downloads__quality-group">
            <Select
              v-model="quality"
              class="downloads__quality"
              :options="qualityOptions"
              :aria-label="t('legacy.dlDefaultQuality')"
              data-testid="downloads-quality"
            />
          </ToolbarGroup>
          <ToolbarGroup class="downloads__submit-group">
            <Button type="submit" :loading="adding" data-testid="downloads-add">
              {{ t("legacy.dlAddSubmit") }}
            </Button>
            <Button
              type="button"
              variant="outlined"
              data-testid="downloads-add-archive"
              @click="openArchive"
            >
              {{ t("legacy.dlAddArchive") }}
            </Button>
          </ToolbarGroup>
        </Toolbar>
      </form>
    </section>

    <Toolbar class="downloads__filters" size="lg" testid="downloads-filters">
      <div class="downloads__filter-scroll">
        <SegmentedControl
          :model-value="filter"
          :options="statusOptions"
          :label="t('downloads.page.statusLabel')"
          testid="downloads-status-segmented"
          @update:model-value="onFilterChange"
        />
      </div>
      <Menu
        class="downloads__more"
        :label="t('downloads.page.more')"
        align="end"
        testid="downloads-more"
      >
        <template #default="{ close }">
          <div class="downloads__menu">
            <Button
              variant="text"
              icon="retry"
              data-testid="downloads-retry-all"
              @click="close(); dialog = 'retry-all'"
            >
              {{ t("legacy.retryAll") }}
            </Button>
            <Button
              variant="text"
              icon="clear"
              data-testid="downloads-clear-success"
              @click="close(); dialog = 'clear-success'"
            >
              {{ t("legacy.clearSuccessDl") }}
            </Button>
          </div>
        </template>
      </Menu>
    </Toolbar>

    <SelectionBar
      :count="selected.length"
      :label="t('downloads.page.selected', { n: selected.length })"
      testid="downloads-selection"
      @clear="clearSelection"
    >
      <Button
        variant="tonal"
        icon="retry"
        data-testid="downloads-retry-selected"
        @click="retrySelected"
      >
        {{ t("legacy.retrySelected") }}
      </Button>
      <template #danger>
        <Button
          variant="outlined"
          danger
          icon="delete"
          data-testid="downloads-delete-selected"
          @click="openDeleteSelected"
        >
          {{ t("legacy.deleteSel") }}
        </Button>
      </template>
    </SelectionBar>

    <ErrorState
      v-if="error && !items.length"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('common.retry')"
      @retry="load"
    />

    <div v-else-if="loading" class="downloads__list" aria-hidden="true">
      <Skeleton v-for="index in 4" :key="index" variant="list" />
    </div>

    <EmptyState
      v-else-if="!items.length"
      :title="t('legacy.noTasks')"
      :body="t('legacy.dlAddHint')"
      testid="downloads-empty"
    />

    <template v-else>
      <div class="downloads__listbar" data-testid="downloads-listbar">
        <Checkbox
          :model-value="allCurrentSelected"
          :indeterminate="hasSelection && !allCurrentSelected"
          :label="t('legacy.selectAll')"
          data-testid="downloads-select-all"
          @change="selectAll"
        />
        <span class="downloads__listbar-count">
          {{ t("downloads.page.shown", { shown: items.length, total }) }}
        </span>
      </div>

      <ul class="downloads__list" data-testid="downloads-list">
        <li
          v-for="task in items"
          :key="task.id"
          class="download-item"
          :class="{
            'download-item--selected': isSelected(task.id),
            'download-item--paused': paused && isLive(task),
          }"
          :data-task-id="task.id"
          :data-status="task.status"
        >
          <Checkbox
            class="download-item__check"
            :model-value="isSelected(task.id)"
            :aria-label="t('downloads.page.selectTask', { title: task.title || task.gid })"
            @change="(checked: boolean) => toggleSelected(task.id, checked)"
          />

          <GalleryThumb
            class="download-item__thumb"
            data-testid="downloads-thumb"
            :src="task.cover_url"
            :alt="task.title || `gid ${task.gid}`"
          />

          <div class="download-item__main">
            <div class="download-item__head">
              <h3 class="download-item__title" :title="task.title">
                {{ task.title || `gid ${task.gid}` }}
              </h3>
              <span class="download-item__badge">{{ badgeText(task) }}</span>
            </div>

            <p
              class="download-item__meta"
              data-testid="downloads-task-meta"
              :title="metaText(task)"
            >
              <span class="download-item__state" :data-status="task.status">
                <Icon :name="statusIcon(task.status)" size="dense" aria-hidden="true" />
                <span>{{ statusText(task) }}</span>
              </span>
              <template v-if="taskMeta(task)">
                <span class="download-item__sep" aria-hidden="true">·</span>
                <span>{{ taskMeta(task) }}</span>
              </template>
              <template v-if="task.status === 'downloading' && progressOf(task) !== null">
                <span class="download-item__sep" aria-hidden="true">·</span>
                <span>{{ progressOf(task) }}%</span>
              </template>
              <template v-if="task.status === 'downloading' && formatSpeed(task.speed)">
                <span class="download-item__sep" aria-hidden="true">·</span>
                <span>{{ t("downloads.progress.speed") }} {{ formatSpeed(task.speed) }}</span>
              </template>
              <template v-if="task.status === 'downloading' && formatDuration(task.eta_seconds)">
                <span class="download-item__sep" aria-hidden="true">·</span>
                <span>{{ t("downloads.progress.eta") }} {{ formatDuration(task.eta_seconds) }}</span>
              </template>
              <template v-if="task.status === 'downloading' && progressOf(task) === null">
                <span class="download-item__sep" aria-hidden="true">·</span>
                <span>{{ t("downloads.progress.enumerating") }}</span>
              </template>
            </p>

            <div
              class="download-item__track"
              :class="{
                'download-item__track--active': progressOf(task) !== null,
                'download-item__track--indeterminate':
                  task.status === 'downloading' && progressOf(task) === null,
              }"
              :role="task.status === 'downloading' ? 'progressbar' : undefined"
              :aria-valuenow="
                task.status === 'downloading' ? (progressOf(task) ?? undefined) : undefined
              "
              :aria-valuemin="task.status === 'downloading' ? 0 : undefined"
              :aria-valuemax="task.status === 'downloading' ? 100 : undefined"
            >
              <span
                v-if="progressOf(task) !== null"
                class="download-item__fill"
                :data-status="task.status"
                :style="{ width: `${progressOf(task)}%` }"
              />
            </div>
          </div>

          <div class="download-item__actions">
            <IconButton
              v-if="isLive(task)"
              :label="t('legacy.cancelDl')"
              name="close"
              size="sm"
              data-testid="downloads-cancel"
              @click="cancel(task.id)"
            />
            <IconButton
              v-if="task.status === 'failed' || task.status === 'cancelled'"
              :label="t('legacy.retry')"
              name="retry"
              size="sm"
              data-testid="downloads-retry"
              @click="retry(task.id)"
            />
            <IconButton
              v-if="canOpenGallery(task)"
              :label="t('downloads.page.open')"
              name="external-link"
              size="sm"
              data-testid="downloads-open"
              @click="openGallery(task)"
            />
            <IconButton
              :label="t('legacy.deleteDl')"
              name="delete"
              size="sm"
              data-testid="downloads-delete"
              @click="openDelete(task.id)"
            />
          </div>
        </li>
      </ul>

      <div class="downloads__footer">
        <Pager
          :page="page"
          :total-pages="pageCount"
          :page-size="pageSize"
          :page-size-options="pageSizeChoices"
          testid="downloads-pager"
          @update:page="goPage"
          @update:page-size="onPageSize"
        />
      </div>
    </template>

    <Dialog
      :open="dialog === 'delete' || dialog === 'delete-selected'"
      :title="t('legacy.deleteDl')"
      testid="downloads-delete-dialog"
      @close="dialog = ''"
    >
      <p v-if="dialog === 'delete-selected'">
        {{ t("downloads.page.confirmDeleteSelected", { n: pendingDelete.length }) }}
      </p>
      <p v-else>{{ t("downloads.page.confirmDelete", { id: pendingDelete[0] ?? "" }) }}</p>
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button data-testid="downloads-delete-confirm" @click="confirmDelete">
          {{ t("legacy.deleteDl") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="dialog === 'clear-success'"
      :title="t('legacy.clearSuccessDl')"
      testid="downloads-clear-dialog"
      @close="dialog = ''"
    >
      <p>{{ t("legacy.confirmClearSuccessDl") }}</p>
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button data-testid="downloads-clear-confirm" @click="clearSuccess">
          {{ t("legacy.clearSuccessDl") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="dialog === 'retry-all'"
      :title="t('legacy.retryAll')"
      testid="downloads-retry-all-dialog"
      @close="dialog = ''"
    >
      <p>{{ t("legacy.retryAllConfirm") }}</p>
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button data-testid="downloads-retry-all-confirm" @click="retryAll">
          {{ t("legacy.retryAll") }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      :open="dialog === 'archive'"
      :title="t('legacy.dlAddArchive')"
      testid="downloads-archive-dialog"
      @close="dialog = ''"
    >
      <Select
        v-model="archiveQuality"
        :options="archiveQualityOptions"
        :label="t('downloads.batch.archiveTier')"
      />
      <template #footer>
        <Button variant="text" @click="dialog = ''">{{ t("common.cancel") }}</Button>
        <Button :loading="adding" data-testid="downloads-archive-confirm" @click="addDownloads(true)">
          {{ t("legacy.dlAddArchive") }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.downloads {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.downloads__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--gv-space-2);
}

.downloads__paused {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-chip);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
  font: var(--gv-type-label-medium);
}

.downloads__quota {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
}

.downloads__quota--warn {
  color: var(--gv-color-warning);
}

.downloads__add {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.downloads__add-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.downloads__add-title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.downloads__add-hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.downloads__add-form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.downloads__quality {
  flex: 1 1 180px;
  min-width: 0;
  max-width: 280px;
}

.downloads__filter-scroll {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  overflow-x: auto;
  padding: 2px;
  scrollbar-width: thin;
}

/* Keep the segmented control at its natural width so the labels are never
   ellipsised; the row scrolls instead. */
.downloads__filter-scroll .segmented {
  min-width: max-content;
}

.downloads__menu {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 180px;
}

.downloads__menu :deep(.btn) {
  justify-content: flex-start;
}

.downloads__listbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-control-lg);
}

.downloads__listbar-count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
}

.downloads__list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.download-item {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--gv-space-2);
  min-height: calc(var(--gv-size-control-lg) * 2);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.download-item--selected {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

.download-item--paused {
  background: var(--gv-color-surface-container-highest);
}

.download-item__check {
  min-height: 0;
}

.download-item__thumb {
  width: 48px;
  height: 62px;
}

.download-item__main {
  display: grid;
  grid-template-rows: auto auto auto;
  gap: var(--gv-space-1);
  min-width: 0;
}

.download-item__head {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.download-item__title {
  overflow: hidden;
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-item__badge {
  display: inline-flex;
  flex: none;
  align-items: center;
  height: var(--gv-size-icon-md);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.download-item__meta {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--gv-space-1);
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.download-item__meta > span:not(.download-item__state):not(.download-item__sep) {
  overflow: hidden;
  text-overflow: ellipsis;
}

.download-item__state {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
}

.download-item__state[data-status="downloading"] {
  color: var(--gv-color-primary-text);
}

.download-item__state[data-status="success"] {
  color: var(--gv-color-success);
}

.download-item__state[data-status="failed"] {
  color: var(--gv-color-error);
}

.download-item__sep {
  color: var(--gv-color-outline);
}

.download-item__track {
  position: relative;
  height: 4px;
  overflow: hidden;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.download-item__track:not(.download-item__track--active) {
  background: color-mix(in srgb, var(--gv-color-outline-variant) 60%, transparent);
}

.download-item__fill {
  display: block;
  height: 100%;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  transition: width var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.download-item__fill[data-status="success"] {
  background: var(--gv-color-success);
}

.download-item__fill[data-status="failed"] {
  background: var(--gv-color-error);
}

.download-item__track--indeterminate::after {
  content: "";
  position: absolute;
  inset: 0;
  width: 40%;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  animation: download-indeterminate 1.2s ease-in-out infinite;
}

@keyframes download-indeterminate {
  from {
    transform: translateX(-100%);
  }

  to {
    transform: translateX(250%);
  }
}

.download-item__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-3);
}

.downloads__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3) 0;
}

@media (max-width: 599.98px) {
  .downloads__add {
    padding: var(--gv-space-2);
  }

  /* One line at 390: the quality select shrinks, the two buttons keep their
     intrinsic width, so the row still shares a single centre line. */
  .downloads__add-actions {
    flex-wrap: nowrap;
    gap: var(--gv-space-2);
  }

  .downloads__add-actions :deep(.toolbar-group) {
    flex-wrap: nowrap;
    gap: var(--gv-space-2);
  }

  .downloads__quality-group {
    flex: 1 1 auto;
    min-width: 0;
  }

  .downloads__submit-group {
    flex: none;
  }

  .downloads__quality {
    flex: 1 1 auto;
    min-width: 0;
  }

  .download-item {
    gap: var(--gv-space-1);
    padding: var(--gv-space-2);
  }

  .download-item__title {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    min-height: calc(var(--gv-type-title-small-line) * 2);
    overflow: hidden;
    white-space: normal;
  }

  .download-item__thumb {
    width: 40px;
    height: 52px;
  }

  .download-item__actions {
    gap: var(--gv-space-2);
  }
}

@media (prefers-reduced-motion: reduce) {
  .download-item__fill {
    transition-duration: 1ms;
  }

  .download-item__track--indeterminate::after {
    animation: none;
  }
}
</style>
