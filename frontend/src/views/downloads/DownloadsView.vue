<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
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
import { ensureDownloadsMessages } from "./messages";
import { startVisiblePolling, type VisiblePoller } from "./poll";
import {
  errorSummary,
  formatDuration,
  formatSpeed,
  parseDownloadLinks,
  taskPercent,
} from "./format";

ensureDownloadsMessages();

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
const dialog = ref<"" | "delete" | "delete-selected" | "clear-success" | "retry-all" | "archive">("");
const pendingDelete = ref<number[]>([]);
const archiveQuality = ref<DownloadQuality>("resample");
let requestSeq = 0;
let poller: VisiblePoller | null = null;

const pageSize = computed(() => clampPageSize(settings.pageSize, 24));
const pageCount = computed(() =>
  Math.max(1, Math.ceil(total.value / Math.max(1, pageSize.value))),
);
const pageLinks = computed(() => {
  const start = Math.max(1, page.value - 2);
  const end = Math.min(pageCount.value, page.value + 2);
  const pages: number[] = [];
  for (let value = start; value <= end; value += 1) pages.push(value);
  return pages;
});
const hasSelection = computed(() => selected.value.length > 0);
const allCurrentSelected = computed(
  () => items.value.length > 0 && items.value.every((item) => selected.value.includes(item.id)),
);
const pageSizeOptions = computed(() =>
  PAGE_SIZES.map((value) => ({ value: String(value), label: String(value) })),
);
const statusOptions = computed(() =>
  FILTERS.map((value) => ({
    value,
    label: value === "all" ? t("legacy.filterAll") : statusLabel(value),
  })),
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

function isArchiveTask(task: DownloadTask): boolean {
  return Boolean(task.mode && task.mode.includes("archive"));
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

function progressOf(task: DownloadTask): number | null {
  return taskPercent(task.current_page, task.total_pages);
}

function isSelected(id: number): boolean {
  return selected.value.includes(id);
}

function toggleSelected(id: number, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
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

function setFilter(value: DownloadStatus | "all"): void {
  filter.value = value;
  void router.push({
    name: "downloads",
    query: value === "all" ? {} : { filter: value },
  });
}

function onPageSize(value: string): void {
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
  } catch (cause) {
    actionError(cause);
  }
}

async function retry(id: number): Promise<void> {
  try {
    await retryDownload(id);
    ui.success(`#${id} ${t("legacy.dlQueued")}`);
    await refreshSilently();
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
    <header class="downloads__header">
      <p class="downloads__eyebrow">{{ t("downloads.page.eyebrow") }}</p>
      <h1 class="downloads__title">{{ t("legacy.downloads") }}</h1>
      <p class="downloads__subtitle">{{ t("legacy.downloadsSub") }}</p>
    </header>

    <div class="downloads__statusbar">
      <Button
        :variant="paused ? 'filled' : 'outlined'"
        :loading="pauseBusy"
        data-testid="downloads-pause"
        @click="togglePause"
        :title="t('legacy.pauseHint')"
      >
        {{ paused ? t("legacy.resume") : t("legacy.pause") }}
        <span aria-hidden="true">{{ paused ? "▶" : "⏸" }}</span>
      </Button>
      <span v-if="paused" class="downloads__paused" data-testid="downloads-paused-badge">
        {{ t("legacy.paused") }}
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
      <span class="downloads__hint">{{ t("downloads.poll.hidden") }}</span>
    </div>

    <section class="downloads__add" :aria-label="t('legacy.dlAddTitle')">
      <div class="downloads__add-head">
        <h2 class="downloads__add-title">{{ t("legacy.dlAddTitle") }}</h2>
        <span class="downloads__add-hint">{{ t("legacy.dlAddHint") }}</span>
      </div>
      <form class="downloads__add-form" @submit.prevent="addDownloads(false)">
        <textarea
          v-model="urls"
          class="downloads__textarea"
          rows="2"
          data-testid="downloads-urls"
          :placeholder="t('legacy.dlAddPlaceholder')"
        />
        <div class="downloads__add-actions">
          <Select
            v-model="quality"
            class="downloads__quality"
            :options="qualityOptions"
            :label="t('legacy.dlDefaultQuality')"
            data-testid="downloads-quality"
          />
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
        </div>
      </form>
    </section>

    <div class="downloads__tasks-head">
      <h2 class="downloads__section-title">{{ t("legacy.dlTasks") }}</h2>
      <span class="downloads__total">{{ total }}</span>
    </div>

    <div class="downloads__filters" role="group" :aria-label="t('legacy.dlTasks')">
      <button
        v-for="option in statusOptions"
        :key="option.value"
        type="button"
        class="downloads__filter"
        :class="{ 'downloads__filter--active': filter === option.value }"
        :aria-pressed="filter === option.value"
        :data-testid="`downloads-filter-${option.value}`"
        @click="setFilter(option.value)"
      >
        {{ option.label }}
      </button>
    </div>

    <div class="downloads__toolbar">
      <Button variant="outlined" size="compact" data-testid="downloads-select-all" @click="selectAll">
        {{ t("legacy.selectAll") }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        data-testid="downloads-retry-selected"
        @click="retrySelected"
      >
        {{ t("legacy.retrySelected") }}
      </Button>
      <Button
        variant="outlined"
        size="compact"
        data-testid="downloads-retry-all"
        @click="dialog = 'retry-all'"
      >
        {{ t("legacy.retryAll") }}
      </Button>
      <Button
        variant="text"
        size="compact"
        data-testid="downloads-delete-selected"
        @click="openDeleteSelected"
      >
        {{ t("legacy.deleteSel") }}
      </Button>
      <Button
        variant="text"
        size="compact"
        data-testid="downloads-clear-success"
        @click="dialog = 'clear-success'"
      >
        {{ t("legacy.clearSuccessDl") }}
      </Button>
    </div>

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

    <ul v-else class="downloads__list" data-testid="downloads-list">
      <li
        v-for="task in items"
        :key="task.id"
        class="download-item"
        :class="{
          'download-item--selected': isSelected(task.id),
          'download-item--paused': paused && (task.status === 'pending' || task.status === 'downloading'),
        }"
        :data-task-id="task.id"
        :data-status="task.status"
      >
        <label class="download-item__check">
          <input
            type="checkbox"
            :checked="isSelected(task.id)"
            :aria-label="t('downloads.page.selectTask', { title: task.title || task.gid })"
            @change="toggleSelected(task.id, $event)"
          />
        </label>

        <div class="download-item__main">
          <div class="download-item__head">
            <h3 class="download-item__title" :title="task.title">
              {{ task.title || `gid ${task.gid}` }}
            </h3>
            <span class="download-item__badge">{{ badgeText(task) }}</span>
          </div>

          <div class="download-item__progress">
            <div
              v-if="task.status === 'downloading'"
              class="download-item__bar"
              :class="{ 'download-item__bar--indeterminate': progressOf(task) === null }"
              role="progressbar"
              :aria-valuenow="progressOf(task) ?? undefined"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <span
                v-if="progressOf(task) !== null"
                class="download-item__bar-fill"
                :style="{ width: `${progressOf(task)}%` }"
              />
            </div>
            <p class="download-item__meta" data-testid="downloads-task-meta">
              <span>{{ statusText(task) }}</span>
              <span v-if="taskMeta(task)"> · {{ taskMeta(task) }}</span>
              <span v-if="task.status === 'downloading' && progressOf(task) !== null">
                · {{ progressOf(task) }}%
              </span>
              <span v-if="task.status === 'downloading' && formatSpeed(task.speed)">
                · {{ t("downloads.progress.speed") }} {{ formatSpeed(task.speed) }}
              </span>
              <span v-if="task.status === 'downloading' && formatDuration(task.eta_seconds)">
                · {{ t("downloads.progress.eta") }} {{ formatDuration(task.eta_seconds) }}
              </span>
              <span v-if="task.status === 'downloading' && progressOf(task) === null">
                · {{ t("downloads.progress.enumerating") }}
              </span>
            </p>
          </div>
        </div>

        <div class="download-item__actions">
          <Button
            v-if="task.status === 'pending' || task.status === 'downloading'"
            variant="outlined"
            size="compact"
            data-testid="downloads-cancel"
            @click="cancel(task.id)"
          >
            {{ t("legacy.cancelDl") }}
          </Button>
          <Button
            v-if="task.status === 'failed' || task.status === 'cancelled' || task.status === 'success'"
            variant="outlined"
            size="compact"
            data-testid="downloads-retry"
            @click="retry(task.id)"
          >
            {{ t("legacy.retry") }}
          </Button>
          <Button
            variant="text"
            size="compact"
            data-testid="downloads-delete"
            @click="openDelete(task.id)"
          >
            {{ t("legacy.deleteDl") }}
          </Button>
        </div>
      </li>
    </ul>

    <div v-if="items.length" class="downloads__footer">
      <nav class="downloads__pager" :aria-label="t('legacy.pageNav')">
        <RouterLink
          v-if="page > 1"
          class="downloads__page"
          :to="{ name: 'downloads', query: { ...route.query, page: page - 1 } }"
        >
          ‹
        </RouterLink>
        <RouterLink
          v-for="value in pageLinks"
          :key="value"
          class="downloads__page"
          :class="{ 'downloads__page--current': value === page }"
          :aria-current="value === page ? 'page' : undefined"
          :to="{ name: 'downloads', query: { ...route.query, page: value } }"
        >
          {{ value }}
        </RouterLink>
        <RouterLink
          v-if="page < pageCount"
          class="downloads__page"
          :to="{ name: 'downloads', query: { ...route.query, page: page + 1 } }"
        >
          ›
        </RouterLink>
      </nav>
      <Select
        class="downloads__page-size"
        :model-value="String(pageSize)"
        :options="pageSizeOptions"
        :label="t('legacy.perPage')"
        data-testid="downloads-page-size"
        @update:model-value="onPageSize"
      />
    </div>

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

.downloads__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.downloads__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.downloads__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.downloads__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.downloads__statusbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-3);
}

.downloads__paused {
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
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

.downloads__hint {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.downloads__add {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.downloads__add-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.downloads__add-title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.downloads__add-hint {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.downloads__add-form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.downloads__textarea {
  width: 100%;
  min-height: 64px;
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  resize: vertical;
}

.downloads__textarea:focus {
  outline: none;
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 1px var(--gv-color-primary);
}

.downloads__add-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: flex-end;
  gap: var(--gv-space-2);
}

.downloads__quality {
  min-width: 180px;
}

.downloads__tasks-head {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
}

.downloads__section-title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.downloads__total {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.downloads__filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.downloads__filter {
  min-height: 32px;
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.downloads__filter--active {
  border-color: var(--gv-color-primary);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.downloads__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
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
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  min-height: 72px;
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.download-item--selected {
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 2px var(--gv-color-primary);
}

.download-item--paused {
  background: var(--gv-color-surface-container-highest);
}

.download-item__check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
}

.download-item__check input {
  width: 20px;
  height: 20px;
  accent-color: var(--gv-color-primary);
  cursor: pointer;
}

.download-item__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.download-item__head {
  display: flex;
  align-items: baseline;
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
  flex: 0 0 auto;
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
}

.download-item__progress {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.download-item__bar {
  position: relative;
  height: 4px;
  overflow: hidden;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.download-item__bar-fill {
  display: block;
  height: 100%;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  transition: width var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.download-item__bar--indeterminate::after {
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

.download-item__meta {
  display: flex;
  flex-wrap: wrap;
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.download-item__actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.downloads__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3) 0;
}

.downloads__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.downloads__page {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.downloads__page:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.downloads__page--current {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.downloads__page-size {
  min-width: 120px;
}

@media (max-width: 599px) {
  .download-item {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .download-item__actions {
    width: 100%;
    justify-content: flex-end;
  }

  .downloads__add-actions {
    justify-content: stretch;
  }
}

@media (prefers-reduced-motion: reduce) {
  .download-item__bar-fill {
    transition-duration: 1ms;
  }

  .download-item__bar--indeterminate::after {
    animation: none;
  }
}
</style>
