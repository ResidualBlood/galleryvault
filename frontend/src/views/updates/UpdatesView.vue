<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
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
import PagerBar from "@/views/updates/components/PagerBar.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();
const { t, te } = useI18n();

const STATES: UpdateState[] = ["active", "pending", "downloading", "failed", "all"];

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
/** Legacy previews the newer gid (data-new-gid) for each selected update. */
const archiveGids = computed(() =>
  items.value
    .filter((item) => selected.value.includes(item.id))
    .map((item) => item.new_gid)
    .filter((gid) => Number.isFinite(gid) && gid > 0),
);
const stateButtons = computed(() =>
  STATES.map((value) => ({
    value,
    label: t(`maintenance.updates.state.${value}`),
  })),
);

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

function setState(next: UpdateState): void {
  if (next === state.value) return;
  selected.value = [];
  pushQuery({ state: next, page: undefined });
}

function toggle(id: number): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id];
}

function toggleAll(): void {
  selected.value =
    selected.value.length === items.value.length
      ? []
      : items.value.map((item) => item.id);
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
    <header class="updates__header">
      <p class="updates__eyebrow">{{ t("maintenance.updates.eyebrow") }}</p>
      <h1 class="updates__title">{{ t("maintenance.updates.title") }}</h1>
      <p class="updates__subtitle">{{ t("maintenance.updates.subtitle") }}</p>
      <p class="updates__status" data-testid="updates-status">
        <template v-if="status">
          <span v-if="status.detecting" class="updates__scanning">
            {{ t("maintenance.updates.status.scanning") }}
          </span>
          <span v-if="status.last_detected_at">
            {{ t("maintenance.updates.status.detectedAt", { date: formatDate(status.last_detected_at) }) }}
          </span>
          <span class="updates__count">
            {{ t("maintenance.updates.status.total", { n: (status.counts.failed ?? 0) + (status.counts.pending ?? 0) + (status.counts.downloading ?? 0) }) }}
          </span>
          <span v-if="status.last_error" class="updates__error">
            {{ t("maintenance.updates.status.error", { error: status.last_error }) }}
          </span>
        </template>
      </p>
    </header>

    <div class="updates__filters" role="group" aria-label="state">
      <Button
        v-for="item in stateButtons"
        :key="item.value"
        :variant="state === item.value ? 'tonal' : 'outlined'"
        size="compact"
        :data-testid="`updates-state-${item.value}`"
        @click="setState(item.value)"
      >
        {{ item.label }}
      </Button>
    </div>

    <div class="updates__toolbar">
      <Button data-testid="updates-update" :disabled="!selectedCount" @click="update()">
        {{ t("maintenance.updates.action.update") }}
        <template v-if="selectedCount">({{ selectedCount }})</template>
      </Button>
      <Button
        variant="outlined"
        data-testid="updates-update-original"
        :disabled="!selectedCount"
        @click="update('original')"
      >
        {{ t("maintenance.updates.action.updateOriginal") }}
      </Button>
      <Button
        variant="outlined"
        data-testid="updates-archive"
        :disabled="!selectedCount"
        @click="archiveOpen = true"
      >
        {{ t("maintenance.updates.action.archive") }}
      </Button>
      <Button
        variant="outlined"
        data-testid="updates-ignore"
        :disabled="!selectedCount"
        @click="ignore"
      >
        {{ t("maintenance.updates.action.ignore") }}
      </Button>
      <Button
        v-if="state === 'failed'"
        variant="outlined"
        class="updates__danger"
        data-testid="updates-delete"
        :disabled="!selectedCount"
        @click="deleteOpen = true"
      >
        {{ t("maintenance.updates.action.delete") }}
      </Button>
      <Button variant="outlined" data-testid="updates-scan" @click="scan">
        {{ t("maintenance.updates.action.scan") }}
      </Button>
      <label class="updates__check">
        <input type="checkbox" data-testid="updates-select-all" @change="toggleAll" />
        {{ t("maintenance.shared.selectAll") }}
      </label>
      <RouterLink class="updates__link" :to="{ name: 'updates-ignored' }">
        {{ t("maintenance.updates.action.ignoredPage") }}
      </RouterLink>
    </div>

    <div v-if="loading" class="updates__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 5" :key="index" variant="line" />
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
      :title="t('maintenance.updates.empty')"
      testid="updates-empty"
    />

    <div v-else class="updates__table-wrap">
      <table class="updates__table">
        <thead>
          <tr>
            <th scope="col"></th>
            <th scope="col"></th>
            <th scope="col">{{ t("maintenance.updates.column.gallery") }}</th>
            <th scope="col">{{ t("maintenance.updates.column.gid") }}</th>
            <th scope="col">{{ t("maintenance.updates.column.favorites") }}</th>
            <th scope="col">{{ t("maintenance.updates.column.status") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id" :data-testid="`updates-row-${item.id}`">
            <td>
              <input
                type="checkbox"
                :aria-label="t('maintenance.shared.select')"
                :checked="selected.includes(item.id)"
                :data-testid="`updates-select-${item.id}`"
                @change="toggle(item.id)"
              />
            </td>
            <td>
              <GalleryThumb :src="coverFor(item)" :alt="item.title" />
            </td>
            <td>
              <RouterLink
                class="updates__gallery-link"
                :to="{ name: 'gallery', params: { id: item.gallery_id } }"
              >
                {{ item.title }}
              </RouterLink>
            </td>
            <td class="updates__gid">
              {{ item.old_gid }}
              <span>{{ t("maintenance.updates.toNewer") }}</span>
              {{ item.new_gid }}
            </td>
            <td>
              <RouterLink
                class="updates__badge"
                :to="{ name: 'favorites-list', params: { id: item.favcat } }"
              >
                {{ favcatLabel(item) }}
              </RouterLink>
            </td>
            <td>
              <span class="updates__badge" :data-status="item.status">
                {{ statusLabel(item.status) }}
              </span>
              <Button
                v-if="item.status === 'failed'"
                variant="text"
                size="compact"
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

    <PagerBar
      v-if="total > pageSize"
      :page="page"
      :pages="pages"
      :total="total"
      testid="updates-pager"
      @change="pushQuery({ page: $event })"
    />

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

.updates__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.updates__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.updates__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.updates__subtitle,
.updates__status {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.updates__status {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.updates__scanning {
  color: var(--gv-color-primary-text);
}

.updates__count {
  font-weight: var(--gv-type-label-large-weight);
}

.updates__error {
  color: var(--gv-color-error);
}

.updates__filters,
.updates__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.updates__check {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  padding: 0 var(--gv-space-2);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
}

.updates__link {
  margin-left: auto;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.updates__danger {
  border-color: var(--gv-color-error);
  color: var(--gv-color-error);
}

.updates__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.updates__table-wrap {
  overflow-x: auto;
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
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-medium);
}

.updates__table tbody tr:last-child td {
  border-bottom: 0;
}

.updates__gallery-link {
  color: var(--gv-color-on-surface);
  text-decoration: none;
}

.updates__gallery-link:hover {
  color: var(--gv-color-primary-text);
}

.updates__gid {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.updates__gid span {
  margin: 0 var(--gv-space-1);
}

.updates__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  text-decoration: none;
}

.updates__badge[data-status="failed"] {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.updates__badge[data-status="downloading"] {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.updates__row-error {
  margin: var(--gv-space-1) 0 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

@media (max-width: 599px) {
  .updates__link {
    margin-left: 0;
  }
}
</style>
