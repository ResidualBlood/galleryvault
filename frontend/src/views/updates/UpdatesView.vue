<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl, {
  type SegmentedOption,
} from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ArchiveDialog from "@/components/system/ArchiveDialog.vue";
import {
  deleteUpdates,
  fetchUpdates,
  fetchUpdatesStatus,
  ignoreUpdates,
  runUpdates,
  scanUpdates,
  type GalleryUpdate,
  type UpdateState,
  type UpdatesStatus,
} from "@/api/updates";
import { usePolling } from "@/composables/usePolling";
import { useUiStore } from "@/stores/ui";
import { useSettingsStore } from "@/stores/settings";
import { formatDate } from "@/stores/library";
import { galleryThumbUrl } from "@/views/updates/url";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import ConfirmDialog from "@/views/updates/components/ConfirmDialog.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const { t, te } = useI18n();

/** UP-08: "all" first, one meaning per label ("有更新" = the active bucket). */
const STATES: UpdateState[] = ["all", "active", "pending", "downloading", "failed"];

const items = ref<GalleryUpdate[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
const status = ref<UpdatesStatus | null>(null);
const selected = ref<number[]>([]);
const deleteOpen = ref(false);
const archiveOpen = ref(false);
let seq = 0;

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

const state = computed<UpdateState>(() => {
  const value = first(route.query.state);
  return STATES.includes(value as UpdateState) ? (value as UpdateState) : "active";
});
const page = computed(() => {
  const parsed = Number.parseInt(first(route.query.page), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
});
const pageSize = computed(() => {
  const parsed = Number.parseInt(first(route.query.page_size), 10);
  return Number.isFinite(parsed) && parsed >= 1 && parsed <= 500 ? parsed : settings.pageSize;
});
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const selectedCount = computed(() => selected.value.length);
const hasSelection = computed(() => selected.value.length > 0);
const allSelected = computed(
  () => items.value.length > 0 && selected.value.length === items.value.length,
);
const partialSelection = computed(() => hasSelection.value && !allSelected.value);
const statusCount = computed(() => {
  const counts = status.value?.counts;
  return (counts?.pending ?? 0) + (counts?.downloading ?? 0) + (counts?.failed ?? 0);
});
const lastScan = computed(() =>
  status.value?.last_detected_at
    ? t("maintenance.updates.status.detectedAt", {
        date: formatDate(status.value.last_detected_at),
      })
    : t("maintenance.updates.status.never"),
);
/** Legacy previews the newer gid (data-new-gid) for each selected update. */
const archiveGids = computed(() =>
  items.value
    .filter((item) => selected.value.includes(item.id))
    .map((item) => item.new_gid)
    .filter((gid) => Number.isFinite(gid) && gid > 0),
);
const stateOptions = computed<SegmentedOption[]>(() =>
  STATES.map((value) => ({
    value,
    label: t(`maintenance.updates.state.${value}`),
  })),
);
/** Keep the user's saved page size as a valid option, sorted ascending. */
const pageSizeChoices = computed(() => {
  const values = new Set<number>([settings.pageSize, 24, 48, 96]);
  return [...values].filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
});

function statusLabel(value: string): string {
  const key = `maintenance.updates.state.${value}`;
  return te(key) ? t(key) : value;
}

function favcatLabel(item: GalleryUpdate): string {
  const label = t("maintenance.updates.favcat", {
    n: item.favcat,
    name: item.favcat_name ?? "",
  });
  return label.trim();
}

function coverFor(item: GalleryUpdate): string {
  return item.cover_url || galleryThumbUrl(item.gallery_id);
}

async function loadStatus(): Promise<void> {
  try {
    status.value = await fetchUpdatesStatus();
  } catch {
    /* the header keeps the last successful status */
  }
}

const poller = usePolling(loadStatus, 5000, { immediate: false });

async function load(): Promise<void> {
  const token = ++seq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchUpdates({
      page: page.value,
      page_size: pageSize.value,
      state: state.value,
    });
    if (token !== seq) return;
    items.value = data.items ?? [];
    total.value = data.total ?? 0;
  } catch (cause) {
    if (token !== seq) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (token === seq) loading.value = false;
  }
}

function pushQuery(patch: Record<string, string | number | undefined>): void {
  const query: Record<string, string> = {};
  const merged: Record<string, string | number | undefined> = {
    state: state.value,
    page: page.value > 1 ? page.value : undefined,
    page_size: pageSize.value,
    ...patch,
  };
  for (const [key, value] of Object.entries(merged)) {
    if (value !== undefined && value !== "") query[key] = String(value);
  }
  void router.push({ name: "updates", query });
}

function setState(next: string): void {
  if (next === state.value) return;
  selected.value = [];
  pushQuery({ state: next, page: undefined });
}

function setPageSize(size: number): void {
  selected.value = [];
  pushQuery({ page: undefined, page_size: size });
}

function toggle(id: number): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id];
}

function toggleAll(): void {
  selected.value = allSelected.value ? [] : items.value.map((item) => item.id);
}

function requireSelection(): number[] | null {
  if (!selected.value.length) {
    ui.error(t("maintenance.updates.message.selectedRequired"));
    return null;
  }
  return selected.value;
}

async function scan(): Promise<void> {
  try {
    await scanUpdates();
    ui.success(t("maintenance.updates.message.scanStarted"));
    await loadStatus();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function update(quality?: "original"): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    const result = await runUpdates(ids, quality ? { quality } : {});
    ui.success(
      t("maintenance.updates.message.updated", { n: result.started ?? ids.length }) +
        (result.skipped
          ? ` · ${t("maintenance.updates.message.skipped", { n: result.skipped })}`
          : ""),
    );
    selected.value = [];
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function archive(payload: { gids: number[]; quality: "resample" | "original" }): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    const result = await runUpdates(ids, { archive: true, quality: payload.quality });
    ui.success(
      t("maintenance.updates.message.updated", { n: result.started ?? ids.length }) +
        (result.skipped
          ? ` · ${t("maintenance.updates.message.skipped", { n: result.skipped })}`
          : ""),
    );
    selected.value = [];
    archiveOpen.value = false;
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function ignore(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    await ignoreUpdates(ids);
    ui.success(t("maintenance.updates.message.ignored", { n: ids.length }));
    selected.value = [];
    await load();
    await loadStatus();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function remove(): Promise<void> {
  const ids = requireSelection();
  if (!ids) return;
  try {
    await deleteUpdates(ids);
    ui.success(t("maintenance.updates.message.deleted", { n: ids.length }));
    selected.value = [];
    deleteOpen.value = false;
    await load();
    await loadStatus();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

async function retryOne(item: GalleryUpdate): Promise<void> {
  try {
    await runUpdates([item.id]);
    ui.success(t("maintenance.updates.message.updated", { n: 1 }));
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

watch(
  () => [state.value, page.value, pageSize.value] as const,
  () => {
    selected.value = [];
    void load();
  },
  { immediate: true },
);

onMounted(() => {
  void loadStatus();
  poller.start();
});

onBeforeUnmount(() => poller.stop());
</script>

<template>
  <section class="updates" data-testid="updates-view">
    <PageHeader
      :title="t('maintenance.updates.title')"
      :count="total"
      :subtitle="t('maintenance.updates.subtitle')"
      testid="updates-header"
    >
      <template #actions>
        <Button
          variant="text"
          icon-end="chevron-right"
          data-testid="updates-ignored-link"
          @click="router.push({ name: 'updates-ignored' })"
        >
          {{ t("maintenance.updates.action.ignoredPage") }}
        </Button>
      </template>

      <p class="updates__status" data-testid="updates-status">
        <span v-if="status?.detecting" class="updates__scanning">
          <Icon name="retry" size="dense" aria-hidden="true" />
          {{ t("maintenance.updates.status.scanning") }}
        </span>
        <span>{{ lastScan }}</span>
        <span class="updates__counter">
          {{ t("maintenance.updates.status.total", { n: statusCount }) }}
        </span>
        <span v-if="status?.last_error" class="updates__error">
          {{ t("maintenance.updates.status.error", { error: status.last_error }) }}
        </span>
      </p>
    </PageHeader>

    <Toolbar class="updates__toolbar" size="lg" testid="updates-toolbar">
      <Button icon="updates" data-testid="updates-scan" @click="scan">
        {{ t("maintenance.updates.action.scan") }}
      </Button>
      <div class="updates__state-scroll">
        <SegmentedControl
          :model-value="state"
          :options="stateOptions"
          :label="t('maintenance.updates.filterLabel')"
          testid="updates-state-filter"
          @change="setState"
        />
      </div>
    </Toolbar>

    <SelectionBar
      :count="selectedCount"
      :label="t('maintenance.shared.selected', { n: selectedCount })"
      testid="updates-selection"
      @clear="selected = []"
    >
      <Button variant="tonal" icon="downloads" data-testid="updates-update" @click="update()">
        {{ t("maintenance.updates.action.update") }}
      </Button>
      <Button
        variant="outlined"
        data-testid="updates-update-original"
        @click="update('original')"
      >
        {{ t("maintenance.updates.action.updateOriginal") }}
      </Button>
      <Button
        variant="outlined"
        icon="archive"
        data-testid="updates-archive"
        @click="archiveOpen = true"
      >
        {{ t("maintenance.updates.action.archive") }}
      </Button>
      <Button
        variant="outlined"
        icon="status-blocked"
        data-testid="updates-ignore"
        @click="ignore"
      >
        {{ t("maintenance.updates.action.ignore") }}
      </Button>
      <template #danger>
        <Button
          v-if="state === 'failed'"
          variant="outlined"
          danger
          icon="delete"
          data-testid="updates-delete"
          @click="deleteOpen = true"
        >
          {{ t("maintenance.updates.action.delete") }}
        </Button>
      </template>
    </SelectionBar>

    <div v-if="loading" class="updates__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 5" :key="index" variant="list" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!items.length"
      icon="updates"
      :title="t('maintenance.updates.empty')"
      :body="t('maintenance.updates.emptyBody')"
      :action-label="t('maintenance.updates.action.scan')"
      testid="updates-empty"
      @action="scan"
    />

    <template v-else>
      <div class="updates__listbar" data-testid="updates-listbar">
        <Checkbox
          :model-value="allSelected"
          :indeterminate="partialSelection"
          :label="t('maintenance.shared.selectAll')"
          data-testid="updates-select-all"
          @change="toggleAll"
        />
        <span class="updates__listbar-count">
          {{ t("maintenance.updates.listCount", { n: items.length, total }) }}
        </span>
      </div>

      <div class="updates__table-wrap">
        <table class="updates__table" data-testid="updates-table">
          <thead>
            <tr>
              <th scope="col" class="updates__col-check">
                <span class="sr-only">{{ t("maintenance.shared.selectAll") }}</span>
              </th>
              <th scope="col" class="updates__col-thumb">
                <span class="sr-only">{{ t("maintenance.updates.column.cover") }}</span>
              </th>
              <th scope="col">{{ t("maintenance.updates.column.gallery") }}</th>
              <th scope="col">{{ t("maintenance.updates.column.gid") }}</th>
              <th scope="col">{{ t("maintenance.updates.column.favorites") }}</th>
              <th scope="col">{{ t("maintenance.updates.column.status") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in items"
              :key="item.id"
              :class="{ 'updates__row--selected': selected.includes(item.id) }"
              :data-testid="`updates-row-${item.id}`"
            >
              <td class="updates__cell updates__cell--check">
                <Checkbox
                  :model-value="selected.includes(item.id)"
                  :aria-label="t('maintenance.shared.select')"
                  role="checkbox"
                  :aria-checked="selected.includes(item.id)"
                  :data-testid="`updates-select-${item.id}`"
                  @change="toggle(item.id)"
                />
              </td>
              <td class="updates__cell updates__cell--thumb">
                <GalleryThumb :src="coverFor(item)" :alt="item.title" />
              </td>
              <td class="updates__cell updates__cell--title">
                <RouterLink
                  class="updates__gallery-link"
                  :to="{ name: 'gallery', params: { id: item.gallery_id } }"
                >
                  {{ item.title }}
                </RouterLink>
              </td>
              <td class="updates__cell updates__cell--gid">
                <span class="updates__gid-old">{{ item.old_gid }}</span>
                <Icon name="forward" size="dense" aria-hidden="true" />
                <span class="sr-only">{{ t("maintenance.updates.toNewer") }}</span>
                <span class="updates__gid-new">{{ item.new_gid }}</span>
              </td>
              <td class="updates__cell updates__cell--favcat">
                <RouterLink
                  class="updates__badge"
                  :to="{ name: 'favorites-list', params: { id: item.favcat } }"
                >
                  {{ favcatLabel(item) }}
                </RouterLink>
              </td>
              <td class="updates__cell updates__cell--status">
                <span class="updates__badge" :data-status="item.status">
                  {{ statusLabel(item.status) }}
                </span>
                <Button
                  v-if="item.status === 'failed'"
                  variant="text"
                  size="sm"
                  icon="retry"
                  data-testid="updates-retry"
                  @click="retryOne(item)"
                >
                  {{ t("maintenance.updates.action.retry") }}
                </Button>
                <p v-if="item.error_message" class="updates__row-error">
                  {{ item.error_message }}
                </p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="total > pageSize" class="updates__footer">
        <Pager
          :page="page"
          :total-pages="pages"
          :page-size="pageSize"
          :page-size-options="pageSizeChoices"
          testid="updates-pager"
          @update:page="pushQuery({ page: $event })"
          @update:page-size="setPageSize"
        />
      </div>
    </template>

    <ConfirmDialog
      :open="deleteOpen"
      :title="t('maintenance.updates.deleteConfirmTitle')"
      :body="t('maintenance.updates.deleteConfirmBody', { n: selectedCount })"
      :confirm-label="t('maintenance.updates.action.delete')"
      danger
      testid="updates-delete-dialog"
      @confirm="remove"
      @cancel="deleteOpen = false"
    />

    <ArchiveDialog
      :open="archiveOpen"
      :gids="archiveGids"
      @close="archiveOpen = false"
      @confirm="archive"
    />
  </section>
</template>

<style scoped>
.updates {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.updates__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.updates__scanning {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  color: var(--gv-color-primary-text);
}

.updates__counter {
  display: inline-flex;
  align-items: center;
  height: var(--gv-space-5);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
}

.updates__error {
  color: var(--gv-color-error);
}

.updates__toolbar {
  gap: var(--gv-space-3);
}

.updates__state-scroll {
  display: flex;
  flex: 1 1 auto;
  justify-content: flex-end;
  min-width: 0;
  overflow-x: auto;
  padding: 2px;
  scrollbar-width: thin;
}

.updates__state-scroll :deep(.segmented) {
  min-width: max-content;
}

.updates__listbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
  min-height: var(--gv-size-control-lg);
}

.updates__listbar-count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.updates__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.updates__table-wrap {
  overflow: hidden;
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.updates__table {
  width: 100%;
  border-collapse: collapse;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}

.updates__table th,
.updates__table td {
  padding: var(--gv-space-2) var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  text-align: left;
  vertical-align: middle;
}

.updates__table th {
  height: var(--gv-size-control-lg);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
  white-space: nowrap;
}

.updates__table tbody tr:last-child td {
  border-bottom: 0;
}

.updates__table tbody tr:hover {
  background: var(--gv-color-surface-container-high);
}

.updates__row--selected {
  background: var(--gv-color-secondary-container);
}

.updates__col-check,
.updates__cell--check {
  width: var(--gv-size-touch);
}

.updates__col-thumb,
.updates__cell--thumb {
  width: 72px;
}

.updates__gallery-link {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
}

.updates__gallery-link:hover {
  color: var(--gv-color-primary-text);
}

.updates__cell--gid {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.updates__cell--gid .gv-icon {
  display: inline-block;
  margin: 0 var(--gv-space-1);
  vertical-align: middle;
}

.updates__gid-new {
  color: var(--gv-color-on-surface);
  font-weight: var(--gv-type-label-large-weight);
}

.updates__badge {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-space-5);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  text-decoration: none;
  white-space: nowrap;
}

.updates__badge[data-status="failed"] {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.updates__badge[data-status="downloading"] {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.updates__cell--status {
  white-space: nowrap;
}

.updates__cell--status .btn {
  margin-inline-start: var(--gv-space-1);
}

.updates__row-error {
  margin: var(--gv-space-1) 0 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
  white-space: normal;
}

.updates__footer {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 839.98px) {
  .updates__state-scroll {
    justify-content: flex-start;
  }

  .updates__table-wrap {
    overflow: visible;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
  }

  .updates__table,
  .updates__table tbody,
  .updates__table tr,
  .updates__table td {
    display: block;
  }

  .updates__table thead {
    display: none;
  }

  .updates__table tbody {
    display: flex;
    flex-direction: column;
    gap: var(--gv-space-2);
  }

  .updates__table tbody tr {
    display: grid;
    grid-template-columns: var(--gv-size-touch) 56px minmax(0, 1fr);
    grid-template-areas:
      "check thumb title"
      "check thumb status"
      "check thumb gid"
      "check thumb favcat";
    column-gap: var(--gv-space-3);
    row-gap: var(--gv-space-1);
    padding: var(--gv-space-3);
    border-radius: var(--gv-radius-md);
    background: var(--gv-color-surface-container);
    box-shadow: var(--gv-elev-1);
  }

  .updates__table tbody tr:hover {
    background: var(--gv-color-surface-container);
  }

  .updates__table td {
    width: auto;
    padding: 0;
    border-bottom: 0;
  }

  .updates__cell--check {
    grid-area: check;
    align-self: start;
  }

  .updates__cell--thumb {
    grid-area: thumb;
  }

  .updates__cell--title {
    grid-area: title;
    min-width: 0;
  }

  .updates__cell--title .updates__gallery-link {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    word-break: break-word;
  }

  .updates__cell--status {
    display: flex;
    grid-area: status;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--gv-space-1);
    white-space: normal;
  }

  .updates__cell--status .btn {
    margin-inline-start: 0;
  }

  .updates__cell--gid {
    grid-area: gid;
    padding-left: calc(var(--gv-space-1) * -1);
  }

  .updates__cell--favcat {
    grid-area: favcat;
  }

  .updates__row-error {
    flex-basis: 100%;
  }

  .updates__footer {
    justify-content: flex-start;
  }
}
</style>
