<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Input from "@/components/ui/Input.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Switch from "@/components/ui/Switch.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
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
import { favoriteFolderTitle } from "./items";
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

function folderTitle(folder: EditableFolder): string {
  return favoriteFolderTitle(folder.name, folder.favcat, t);
}

function dotStyle(favcat: number): Record<string, string> {
  return { background: `var(--gv-favcat-${favcat})` };
}

function sizePair(cloud: number, local: number): string {
  return `${cloud ? "~" : ""}${formatBytes(cloud) || "0 B"} / ${formatBytes(local) || "0 B"}`;
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
  <section class="favcats" data-testid="favorites-view">
    <PageHeader
      :title="t('legacy.favcatTitle')"
      :subtitle="t('legacy.favcatSub')"
      testid="favorites-header"
    >
      <template #actions>
        <span v-if="dirty" class="favcats__dirty">{{ t("favorites.page.dirty") }}</span>
        <Button
          data-testid="favorites-save"
          :variant="dirty ? 'filled' : 'text'"
          :loading="saving"
          :disabled="!dirty"
          icon="check"
          @click="save"
        >
          {{ t("legacy.save") }}
        </Button>
      </template>
    </PageHeader>

    <Toolbar testid="favorites-toolbar">
      <ToolbarGroup collapsible :label="t('legacy.syncFavcats')">
        <Button
          data-testid="favorites-sync"
          variant="outlined"
          icon="retry"
          @click="syncNames"
        >
          {{ t("legacy.syncFavcats") }}
        </Button>
      </ToolbarGroup>
      <ToolbarGroup collapsible :label="t('legacy.downloadMissing')">
        <Button
          data-testid="favorites-download-missing"
          variant="outlined"
          icon="downloads"
          @click="downloadMissing"
        >
          {{ t("legacy.downloadMissing") }}
        </Button>
      </ToolbarGroup>
      <ToolbarGroup end>
        <Button
          data-testid="favorites-check-all"
          variant="tonal"
          icon="integrity"
          @click="checkAll"
        >
          {{ t("legacy.checkAll") }}
        </Button>
        <RouterLink class="favcats__link" to="/updates">
          {{ t("legacy.galleryUpdates") }}
        </RouterLink>
      </ToolbarGroup>
    </Toolbar>

    <ErrorState
      v-if="loadError && !folders.length"
      :title="t('common.errorTitle')"
      :body="loadError"
      :retry-label="t('common.retry')"
      @retry="loadFolders"
    />

    <div v-else-if="loading" class="favcats__skeletons" data-testid="favorites-loading">
      <Skeleton v-for="index in 4" :key="index" variant="list" />
    </div>

    <EmptyState
      v-else-if="!folders.length"
      :title="t('legacy.noGalleries')"
      :body="t('legacy.favHint')"
      testid="favorites-empty"
    />

    <div v-else class="favcats__table" data-testid="favorites-table" role="table">
      <div class="favcats__row favcats__row--head" role="row">
        <span role="columnheader">{{ t("legacy.favorites") }}</span>
        <span role="columnheader" :title="t('favorites.page.cloudLocalHint')">
          {{ t("favorites.page.countColumn") }}
        </span>
        <span role="columnheader" :title="t('favorites.page.cloudLocalHint')">
          {{ t("favorites.page.sizeColumn") }}
        </span>
        <span role="columnheader">{{ t("legacy.enabled") }}</span>
        <span role="columnheader">{{ t("legacy.mode") }}</span>
        <span role="columnheader">{{ t("favorites.page.interval") }}</span>
        <span role="columnheader" class="favcats__head-action">{{ t("legacy.checkNow") }}</span>
      </div>

      <div
        v-for="folder in folders"
        :key="folder.favcat"
        class="favcats__row"
        role="row"
        data-testid="favcat-row"
        :data-favcat="folder.favcat"
      >
        <div class="favcats__name favcats__cell--name" role="cell">
          <span class="favcats__dot" :style="dotStyle(folder.favcat)" aria-hidden="true" />
          <RouterLink class="favcats__name-link" :to="`/favorites/${folder.favcat}`">
            {{ folderTitle(folder) }}
          </RouterLink>
          <span
            v-if="folderStatus(folder.favcat)?.running"
            class="favcats__ring"
            :title="`${folderStatus(folder.favcat)?.done ?? 0} / ${folderStatus(folder.favcat)?.total ?? 0}`"
            data-testid="favcat-ring"
          >
            <svg viewBox="0 0 36 36" aria-hidden="true">
              <circle class="favcats__ring-bg" cx="18" cy="18" r="15.9" />
              <circle
                class="favcats__ring-fg"
                cx="18"
                cy="18"
                r="15.9"
                :stroke-dasharray="String(2 * Math.PI * 15.9)"
                :stroke-dashoffset="ringOffset(folderStatus(folder.favcat)?.done ?? 0, folderStatus(folder.favcat)?.total ?? 0)"
              />
            </svg>
          </span>
        </div>

        <div
          class="favcats__metric favcats__cell--count"
          role="cell"
          :title="t('favorites.page.cloudLocalHint')"
        >
          {{ folder.cloud_count }} / {{ folder.local_count }}
        </div>

        <div
          class="favcats__metric favcats__cell--size"
          role="cell"
          :title="t('favorites.page.cloudLocalHint')"
        >
          {{ sizePair(folder.cloud_size, folder.local_size) }}
        </div>

        <div class="favcats__cell favcats__cell--switch" role="cell">
          <Switch
            :model-value="folder.enabled"
            :label="`${folderTitle(folder)} ${t('legacy.enabled')}`"
            data-testid="favcat-enabled"
            @update:model-value="folder.enabled = $event; markDirty()"
          />
        </div>

        <div class="favcats__cell favcats__cell--mode" role="cell">
          <Select
            :model-value="folder.mode"
            size="md"
            :options="modeOptions"
            :aria-label="`${folderTitle(folder)} ${t('legacy.mode')}`"
            data-testid="favcat-mode"
            @update:model-value="folder.mode = $event; markDirty()"
          />
        </div>

        <div class="favcats__cell favcats__cell--interval" role="cell">
          <Input
            :model-value="String(folder.poll_interval_minutes)"
            size="md"
            type="number"
            :unit="t('favorites.page.minutesUnit')"
            :aria-label="`${folderTitle(folder)} ${t('favorites.page.interval')}`"
            data-testid="favcat-interval"
            @update:model-value="folder.poll_interval_minutes = Number.parseInt($event, 10) || 1"
            @change="markDirty()"
          />
        </div>

        <div class="favcats__cell favcats__cell--action" role="cell">
          <Button
            variant="outlined"
            size="md"
            data-testid="favcat-check"
            @click="checkOne(folder.favcat)"
          >
            {{ t("legacy.checkNow") }}
          </Button>
        </div>
      </div>
    </div>

    <p v-if="statusError" class="favcats__error" role="alert">
      {{ t("favorites.page.checkStatusError") }}: {{ statusError }}
    </p>
  </section>
</template>

<style scoped>
.favcats {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.favcats__dirty {
  color: var(--gv-color-warning);
  font: var(--gv-type-label-medium);
}

.favcats__link {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
  white-space: nowrap;
}

.favcats__link:hover {
  text-decoration: underline;
}

.favcats__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.favcats__table {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.favcats__row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) 120px 180px 88px 190px 170px 140px;
  align-items: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-2) var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.favcats__row:last-child {
  border-bottom: 0;
}

.favcats__row--head {
  padding-block: var(--gv-space-2);
  background: var(--gv-color-surface-container-low);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.favcats__row--head span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.favcats__head-action {
  text-align: end;
}

.favcats__row:not(.favcats__row--head):hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 4%, transparent);
}

.favcats__name {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.favcats__dot {
  flex: none;
  width: var(--gv-space-2);
  height: var(--gv-space-2);
  border-radius: var(--gv-radius-full);
}

.favcats__name-link {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.favcats__name-link:hover {
  color: var(--gv-color-primary-text);
  text-decoration: underline;
}

.favcats__ring {
  display: inline-flex;
  flex: none;
  width: var(--gv-space-5);
  height: var(--gv-space-5);
}

.favcats__ring-bg,
.favcats__ring-fg {
  fill: none;
  stroke-width: 3;
}

.favcats__ring-bg {
  stroke: var(--gv-color-surface-variant);
}

.favcats__ring-fg {
  stroke: var(--gv-color-primary);
  transform: rotate(-90deg);
  transform-origin: center;
}

.favcats__metric {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.favcats__cell {
  display: flex;
  align-items: center;
  min-width: 0;
}

.favcats__cell--action {
  justify-content: flex-end;
}

.favcats__error {
  margin: 0;
  padding: var(--gv-space-2) var(--gv-space-3);
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

@media (max-width: 839px) {
  .favcats__table {
    border: 0;
    background: transparent;
  }

  /* Two-line card: name + switch, then stats, then mode / interval / action.
     No label-value folding (FV-09 note in the audit). */
  .favcats__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 104px 112px;
    grid-template-areas:
      "name name switch"
      "count size size"
      "mode mode interval"
      "action action action";
    align-items: center;
    gap: var(--gv-space-2) var(--gv-space-3);
    margin-bottom: var(--gv-space-2);
    padding: var(--gv-space-3);
    border: 1px solid var(--gv-color-outline-variant);
    border-radius: var(--gv-radius-md);
    background: var(--gv-color-surface-container);
  }

  .favcats__row--head {
    display: none;
  }

  .favcats__cell--name {
    grid-area: name;
  }

  .favcats__cell--switch {
    grid-area: switch;
    justify-content: flex-end;
  }

  .favcats__cell--count {
    grid-area: count;
  }

  .favcats__cell--size {
    grid-area: size;
    justify-content: flex-end;
  }

  .favcats__cell--mode {
    grid-area: mode;
  }

  .favcats__cell--interval {
    grid-area: interval;
  }

  .favcats__cell--action {
    grid-area: action;
    justify-content: flex-end;
  }

  .favcats__cell--mode :deep(.select-field),
  .favcats__cell--interval :deep(.field) {
    width: 100%;
  }
}
</style>
