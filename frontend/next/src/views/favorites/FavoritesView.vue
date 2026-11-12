<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import { useUiStore } from "@/stores/ui";
import { formatBytes } from "@/stores/library";
import {
  checkAllFavorites,
  checkFavoriteCategory,
  downloadMissingFavorites,
  fetchFavoriteCategories,
  fetchFavoriteCheckStatus,
  saveFavoriteMonitorSettings,
  syncFavoriteCategoryNames,
  type FavoriteCategory,
  type FavoriteCheckStatus,
} from "@/api/favorites";
import { ensureFavoritesMessages } from "./messages";

ensureFavoritesMessages();

interface EditableFolder {
  favcat: number;
  name: string;
  cloud_count: number;
  local_count: number;
  cloud_size: number;
  local_size: number;
  enabled: boolean;
  mode: string;
  poll_interval_minutes: number;
}

const { t } = useI18n();
const ui = useUiStore();

// The backend only accepts these three modes. Legacy `favorites_monitor` rows
// can hold a display-only value (e.g. `gallery`); the old frontend's <select>
// silently fell back to the first option, which is what we reproduce here
// instead of echoing an invalid mode back to POST /api/settings (422).
const FAVORITE_MODES = ["incremental", "monitor_only", "force"] as const;

function normalizeFavoriteMode(value: unknown): string {
  return FAVORITE_MODES.includes(value as (typeof FAVORITE_MODES)[number])
    ? String(value)
    : "incremental";
}

const folders = ref<EditableFolder[]>([]);
const loading = ref(true);
const loadError = ref("");
const saving = ref(false);
const dirty = ref(false);
const checkStatus = ref<FavoriteCheckStatus | null>(null);
const statusError = ref("");
let pollTimer: ReturnType<typeof setInterval> | null = null;

const modeOptions = computed(() => [
  { value: "incremental", label: t("legacy.favModeIncremental") },
  { value: "monitor_only", label: t("legacy.favModeMonitorOnly") },
  { value: "force", label: t("legacy.favModeForce") },
]);

function toEditable(item: FavoriteCategory): EditableFolder {
  return {
    favcat: item.favcat,
    name: item.name,
    cloud_count: item.cloud_count ?? 0,
    local_count: item.local_count ?? 0,
    cloud_size: item.cloud_size ?? 0,
    local_size: item.local_size ?? 0,
    enabled: Boolean(item.enabled),
    mode: normalizeFavoriteMode(item.mode),
    poll_interval_minutes: Math.max(1, item.poll_interval_minutes ?? 720),
  };
}

async function loadFolders(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    const categories = await fetchFavoriteCategories();
    folders.value = categories.map(toEditable);
    dirty.value = false;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function refreshCheckStatus(): Promise<void> {
  if (document.visibilityState === "hidden") return;
  try {
    checkStatus.value = await fetchFavoriteCheckStatus();
    statusError.value = "";
  } catch (error) {
    statusError.value = error instanceof Error ? error.message : String(error);
  }
}

function startPolling(): void {
  if (pollTimer !== null) clearInterval(pollTimer);
  void refreshCheckStatus();
  pollTimer = setInterval(() => {
    if (document.visibilityState === "hidden") return;
    void refreshCheckStatus();
  }, 3000);
}

function stopPolling(): void {
  if (pollTimer !== null) clearInterval(pollTimer);
  pollTimer = null;
}

function folderStatus(favcat: number) {
  return checkStatus.value?.categories[String(favcat)] ?? null;
}

function ringOffset(done: number, total: number): string {
  const circumference = 2 * Math.PI * 15.9;
  const ratio = total > 0 ? Math.min(1, Math.max(0, done / total)) : 0;
  return String(circumference * (1 - ratio));
}

function markDirty(): void {
  dirty.value = true;
}

async function save(): Promise<void> {
  if (saving.value) return;
  saving.value = true;
  try {
    await saveFavoriteMonitorSettings(
      folders.value.map((folder) => ({
        favcat: folder.favcat,
        enabled: folder.enabled,
        mode: folder.mode,
        poll_interval_minutes: Math.max(1, Math.trunc(folder.poll_interval_minutes) || 720),
      })),
    );
    dirty.value = false;
    ui.success(t("legacy.saveOk"));
  } catch (error) {
    ui.error(
      error instanceof Error && error.message
        ? error.message
        : t("favorites.page.saveFailed"),
    );
  } finally {
    saving.value = false;
  }
}

async function syncNames(): Promise<void> {
  try {
    await syncFavoriteCategoryNames();
    ui.success(t("favorites.page.syncStarted"));
    await loadFolders();
  } catch (error) {
    ui.error(error instanceof Error ? error.message : t("legacy.error"));
  }
}

async function checkAll(): Promise<void> {
  try {
    await checkAllFavorites();
    ui.success(t("favorites.page.checkStarted"));
    await refreshCheckStatus();
  } catch (error) {
    ui.error(error instanceof Error ? error.message : t("legacy.error"));
  }
}

async function checkOne(favcat: number): Promise<void> {
  try {
    await checkFavoriteCategory(favcat);
    ui.success(`${t("legacy.checkNow")} #${favcat}`);
    await refreshCheckStatus();
  } catch (error) {
    ui.error(error instanceof Error ? error.message : t("legacy.error"));
  }
}

async function downloadMissing(): Promise<void> {
  try {
    await downloadMissingFavorites();
    ui.success(t("legacy.downloadMissingStarted"));
  } catch (error) {
    ui.error(error instanceof Error ? error.message : t("legacy.error"));
  }
}

onMounted(() => {
  void loadFolders();
  startPolling();
});

onBeforeUnmount(stopPolling);
</script>

<template>
  <section class="favorites" data-testid="favorites-view">
    <header class="favorites__header">
      <p class="favorites__eyebrow">{{ t("favorites.page.eyebrow") }}</p>
      <h1 class="favorites__title">{{ t("legacy.favcatTitle") }}</h1>
      <p class="favorites__subtitle">{{ t("legacy.favcatSub") }}</p>
    </header>

    <div class="favorites__toolbar">
      <Button
        data-testid="favorites-save"
        :loading="saving"
        :disabled="!dirty"
        @click="save"
      >
        {{ t("legacy.save") }}
      </Button>
      <Button data-testid="favorites-sync" variant="outlined" @click="syncNames">
        {{ t("legacy.syncFavcats") }}
      </Button>
      <Button data-testid="favorites-check-all" variant="outlined" @click="checkAll">
        {{ t("legacy.checkAll") }}
      </Button>
      <Button
        data-testid="favorites-download-missing"
        variant="outlined"
        @click="downloadMissing"
      >
        {{ t("legacy.downloadMissing") }}
      </Button>
      <RouterLink class="favorites__updates" to="/updates">
        {{ t("legacy.galleryUpdates") }}
      </RouterLink>
      <span v-if="dirty" class="favorites__dirty">{{ t("favorites.page.dirty") }}</span>
    </div>

    <ErrorState
      v-if="loadError && !folders.length"
      :title="t('common.errorTitle')"
      :body="loadError"
      :retry-label="t('common.retry')"
      @retry="loadFolders"
    />

    <p v-else-if="loading" class="favorites__loading">{{ t("legacy.loading") }}</p>

    <EmptyState
      v-else-if="!folders.length"
      :title="t('legacy.noGalleries')"
      :body="t('legacy.favHint')"
      testid="favorites-empty"
    />

    <div v-else class="favorites__table-wrap">
      <table class="favorites__table" data-testid="favorites-table">
        <caption class="sr-only">{{ t("legacy.favcatTitle") }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t("legacy.favorites") }}</th>
            <th scope="col">{{ t("legacy.favCount") }}</th>
            <th scope="col">{{ t("legacy.favSize") }}</th>
            <th scope="col">{{ t("legacy.enabled") }}</th>
            <th scope="col">{{ t("legacy.mode") }}</th>
            <th scope="col">{{ t("legacy.intervalMin") }}</th>
            <th scope="col"><span class="sr-only">{{ t("legacy.checkNow") }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="folder in folders"
            :key="folder.favcat"
            data-testid="favcat-row"
            :data-favcat="folder.favcat"
          >
            <td :data-label="t('legacy.favorites')">
              <RouterLink class="favorites__name" :to="`/favorites/${folder.favcat}`">
                {{ folder.name || t("legacy.favFolderName", { n: folder.favcat }) }}
              </RouterLink>
              <span class="favorites__cat">#{{ folder.favcat }}</span>
              <span
                v-if="folderStatus(folder.favcat)?.running"
                class="favorites__ring"
                :title="`${folderStatus(folder.favcat)?.done ?? 0} / ${folderStatus(folder.favcat)?.total ?? 0}`"
                data-testid="favcat-ring"
              >
                <svg viewBox="0 0 36 36" aria-hidden="true">
                  <circle class="favorites__ring-bg" cx="18" cy="18" r="15.9" />
                  <circle
                    class="favorites__ring-fg"
                    cx="18"
                    cy="18"
                    r="15.9"
                    :stroke-dasharray="String(2 * Math.PI * 15.9)"
                    :stroke-dashoffset="ringOffset(folderStatus(folder.favcat)?.done ?? 0, folderStatus(folder.favcat)?.total ?? 0)"
                  />
                </svg>
              </span>
            </td>
            <td :data-label="t('legacy.favCount')">
              <span class="favorites__metric">{{ folder.cloud_count }} / {{ folder.local_count }}</span>
            </td>
            <td :data-label="t('legacy.favSize')">
              <span class="favorites__metric">
                {{ folder.cloud_size ? "~" : "" }}{{ formatBytes(folder.cloud_size) }} /
                {{ formatBytes(folder.local_size) }}
              </span>
            </td>
            <td :data-label="t('legacy.enabled')">
              <Switch
                :model-value="folder.enabled"
                :label="`${folder.name || folder.favcat} ${t('legacy.enabled')}`"
                data-testid="favcat-enabled"
                @update:model-value="folder.enabled = $event; markDirty()"
              />
            </td>
            <td :data-label="t('legacy.mode')">
              <Select
                class="favorites__mode"
                :model-value="folder.mode"
                :options="modeOptions"
                data-testid="favcat-mode"
                @update:model-value="folder.mode = $event; markDirty()"
              />
            </td>
            <td :data-label="t('legacy.intervalMin')">
              <input
                v-model.number="folder.poll_interval_minutes"
                class="favorites__interval"
                type="number"
                min="1"
                data-testid="favcat-interval"
                @change="markDirty"
              />
            </td>
            <td :data-label="t('legacy.checkNow')">
              <Button
                variant="outlined"
                size="compact"
                data-testid="favcat-check"
                @click="checkOne(folder.favcat)"
              >
                {{ t("legacy.checkNow") }}
              </Button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="statusError" class="favorites__status-error">
        {{ t("favorites.page.checkStatusError") }}: {{ statusError }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.favorites {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.favorites__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.favorites__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.favorites__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.favorites__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.favorites__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.favorites__updates {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0 var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.favorites__updates:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.favorites__dirty {
  color: var(--gv-color-warning);
  font: var(--gv-type-label-medium);
}

.favorites__loading {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.favorites__table-wrap {
  overflow-x: auto;
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.favorites__table {
  width: 100%;
  border-collapse: collapse;
  font: var(--gv-type-body-medium);
}

.favorites__table th {
  padding: var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  text-align: start;
  white-space: nowrap;
}

.favorites__table td {
  padding: var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  color: var(--gv-color-on-surface);
  vertical-align: middle;
}

.favorites__table tbody tr:last-child td {
  border-bottom: 0;
}

.favorites__table tbody tr:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 4%, transparent);
}

.favorites__name {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-title-small);
  text-decoration: none;
}

.favorites__name:hover {
  text-decoration: underline;
}

.favorites__cat {
  margin-inline-start: var(--gv-space-2);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
}

.favorites__ring {
  display: inline-flex;
  width: var(--gv-space-5);
  height: var(--gv-space-5);
  margin-inline-start: var(--gv-space-2);
  vertical-align: middle;
}

.favorites__ring-bg,
.favorites__ring-fg {
  fill: none;
  stroke-width: 3;
}

.favorites__ring-bg {
  stroke: var(--gv-color-surface-variant);
}

.favorites__ring-fg {
  stroke: var(--gv-color-primary);
  transform: rotate(-90deg);
  transform-origin: center;
}

.favorites__metric {
  color: var(--gv-color-on-surface-variant);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.favorites__mode {
  min-width: 148px;
}

.favorites__interval {
  width: 96px;
  height: 40px;
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}

.favorites__interval:focus {
  outline: none;
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 1px var(--gv-color-primary);
}

.favorites__status-error {
  margin: 0;
  padding: var(--gv-space-2) var(--gv-space-3);
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

@media (max-width: 839px) {
  .favorites__table-wrap {
    overflow: visible;
    background: transparent;
    box-shadow: none;
  }

  .favorites__table,
  .favorites__table thead,
  .favorites__table tbody,
  .favorites__table tr,
  .favorites__table td {
    display: block;
    width: 100%;
  }

  .favorites__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }

  .favorites__table tr {
    margin-bottom: var(--gv-space-2);
    padding: var(--gv-space-2) var(--gv-space-3);
    border-radius: var(--gv-radius-md);
    background: var(--gv-color-surface-container);
    box-shadow: var(--gv-elev-1);
  }

  .favorites__table td {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--gv-space-3);
    padding: var(--gv-space-1) 0;
    border-bottom: 0;
  }

  .favorites__table td::before {
    content: attr(data-label);
    color: var(--gv-color-on-surface-variant);
    font: var(--gv-type-label-medium);
  }

  .favorites__table td:first-child {
    justify-content: flex-start;
  }
}
</style>
