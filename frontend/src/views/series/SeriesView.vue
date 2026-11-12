<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Input from "@/components/ui/Input.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import { ApiError } from "@/api/client";
import { downloadGalleryOriginal, redownloadGallery } from "@/api/gallery";
import {
  addSeriesCloudItems,
  createSeries,
  deleteSeries,
  downloadSelectedFavorites,
  fetchSeries,
  fetchSeriesCloudCandidates,
  rebuildSeries,
  removeSeriesCloudItems,
  removeSeriesItems,
  renameSeries,
  type SeriesCloudCandidate,
  type SeriesGroup,
  type SeriesMember,
} from "@/api/series";
import { useSettingsStore } from "@/stores/settings";
import { useUiStore } from "@/stores/ui";
import SeriesMemberCard from "./SeriesMemberCard.vue";
import { ensureSeriesMessages } from "./messages";

ensureSeriesMessages();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const settings = useSettingsStore();
const ui = useUiStore();

const groups = ref<SeriesGroup[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(25);
const loading = ref(true);
const error = ref("");

const localSelection = ref<Set<number>>(new Set());
const cloudSelection = ref<Map<number, number | null>>(new Map());

let controller: AbortController | null = null;

const showAll = computed(() => route.query.show_all === "1");
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const selectedCount = computed(() => localSelection.value.size + cloudSelection.value.size);
const totalItems = computed(() =>
  groups.value.reduce((sum, group) => sum + (group.galleries?.length ?? group.count ?? 0), 0),
);

function message(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof Error) return cause.message;
  return String(cause);
}

function isSelected(member: SeriesMember): boolean {
  if (member.is_local && member.gallery_id) return localSelection.value.has(member.gallery_id);
  if (member.gid) return cloudSelection.value.has(member.gid);
  return false;
}

function toggleMember(member: SeriesMember, checked: boolean): void {
  if (member.is_local && member.gallery_id) {
    const next = new Set(localSelection.value);
    if (checked) next.add(member.gallery_id);
    else next.delete(member.gallery_id);
    localSelection.value = next;
    return;
  }
  if (!member.gid) return;
  const next = new Map(cloudSelection.value);
  if (checked) next.set(member.gid, member.favcat ?? null);
  else next.delete(member.gid);
  cloudSelection.value = next;
}

function clearSelection(): void {
  localSelection.value = new Set();
  cloudSelection.value = new Map();
}

function firstQueryValue(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return typeof value === "string" ? value : "";
}

function clampPage(value: unknown): number {
  const parsed = Number.parseInt(firstQueryValue(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

async function load(): Promise<void> {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  page.value = clampPage(route.query.page ?? "");
  pageSize.value = settings.pageSize || 25;
  try {
    const data = await fetchSeries(
      { page: page.value, page_size: pageSize.value, show_all: showAll.value },
      controller.signal,
    );
    groups.value = data.items ?? [];
    total.value = data.total ?? groups.value.length;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") return;
    error.value = message(cause);
    groups.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function buildQuery(patch: Record<string, string> = {}): Record<string, string> {
  const query: Record<string, string> = {};
  if (showAll.value) query.show_all = "1";
  if (page.value > 1) query.page = String(page.value);
  const merged = { ...query, ...patch };
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(merged)) if (value) out[key] = value;
  return out;
}

function goPage(target: number): void {
  const next = Math.min(totalPages.value, Math.max(1, target));
  void router.push({ name: "series", query: buildQuery({ page: String(next) }) });
}

function toggleShowAll(): void {
  void router.push({
    name: "series",
    query: showAll.value ? {} : { show_all: "1" },
  });
}

// Paging must not clear the selection: users pick members across pages before
// running batch actions. Leaving the route destroys this component anyway.
watch(
  () => route.query,
  () => {
    void load();
  },
);

onMounted(() => {
  void load();
});

onBeforeUnmount(() => {
  controller?.abort();
});

/* ------------------------------------------------------------ create/rename */

const nameDialogOpen = ref(false);
const nameDialogMode = ref<"create" | "rename">("create");
const nameValue = ref("");
const nameTarget = ref<number | null>(null);
const nameError = ref("");
const busy = ref(false);

function openCreate(): void {
  nameDialogMode.value = "create";
  nameTarget.value = null;
  nameValue.value = "";
  nameError.value = "";
  nameDialogOpen.value = true;
}

function openRename(group: SeriesGroup): void {
  nameDialogMode.value = "rename";
  nameTarget.value = group.id;
  nameValue.value = group.name;
  nameError.value = "";
  nameDialogOpen.value = true;
}

async function submitName(): Promise<void> {
  const name = nameValue.value.trim();
  if (!name || busy.value) return;
  busy.value = true;
  nameError.value = "";
  try {
    if (nameDialogMode.value === "create") {
      await createSeries(name);
      ui.success(t("seriesPage.created"));
    } else if (nameTarget.value !== null) {
      await renameSeries(nameTarget.value, name);
      ui.success(t("seriesPage.renamed"));
    }
    nameDialogOpen.value = false;
    await load();
  } catch (cause) {
    nameError.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* ------------------------------------------------------------------ rebuild */

async function rebuild(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    const result = await rebuildSeries();
    ui.success(
      t("seriesPage.rebuilt", {
        created: result.created ?? 0,
        merged: result.merged ?? 0,
      }),
    );
    await load();
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}

/* --------------------------------------------------------------- delete series */

const deleteOpen = ref(false);
const deleteTarget = ref<SeriesGroup | null>(null);

function openDelete(group: SeriesGroup): void {
  deleteTarget.value = group;
  deleteOpen.value = true;
}

async function confirmDelete(): Promise<void> {
  const target = deleteTarget.value;
  if (!target || busy.value) return;
  busy.value = true;
  try {
    await deleteSeries(target.id);
    ui.success(t("seriesPage.deleted"));
    deleteOpen.value = false;
    await load();
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}

/* ----------------------------------------------------------------- add items */

const addOpen = ref(false);
const addTargetId = ref<number | null>(null);
const manualGids = ref("");
const candidateQuery = ref("");
const candidates = ref<SeriesCloudCandidate[]>([]);
const candidateSelection = ref<Set<number>>(new Set());
const candidatesLoading = ref(false);
const addError = ref("");

function parseGids(value: string): number[] {
  return [
    ...new Set(
      value
        .split(/[\s,，]+/)
        .map((part) => Number.parseInt(part, 10))
        .filter((value) => Number.isFinite(value) && value > 0),
    ),
  ];
}

async function loadCandidates(): Promise<void> {
  const target = addTargetId.value;
  if (target === null) return;
  candidatesLoading.value = true;
  try {
    candidates.value = await fetchSeriesCloudCandidates(target, candidateQuery.value.trim());
  } catch {
    candidates.value = [];
  } finally {
    candidatesLoading.value = false;
  }
}

function openAdd(group: SeriesGroup): void {
  addTargetId.value = group.id;
  manualGids.value = "";
  candidateQuery.value = "";
  candidates.value = [];
  candidateSelection.value = new Set();
  addError.value = "";
  addOpen.value = true;
  void loadCandidates();
}

function toggleCandidate(gid: number, checked: boolean): void {
  const next = new Set(candidateSelection.value);
  if (checked) next.add(gid);
  else next.delete(gid);
  candidateSelection.value = next;
}

async function submitAdd(): Promise<void> {
  const target = addTargetId.value;
  if (target === null || busy.value) return;
  const gids = [...new Set([...parseGids(manualGids.value), ...candidateSelection.value])];
  if (!gids.length) {
    addError.value = t("seriesPage.atLeastOne");
    return;
  }
  busy.value = true;
  addError.value = "";
  try {
    const result = await addSeriesCloudItems(target, gids);
    const added = (result.added_local ?? 0) + (result.added_cloud ?? 0);
    ui.success(t("seriesPage.added", { count: added }));
    addOpen.value = false;
    await load();
  } catch (cause) {
    addError.value = message(cause);
  } finally {
    busy.value = false;
  }
}

/* -------------------------------------------------------------- remove items */

const removeOpen = ref(false);
const removeTargetId = ref<number | null>(null);
const removeGids = ref("");
const removeError = ref("");
const removeTargetsLocal = ref<number[]>([]);
const removeTargetsCloud = ref<number[]>([]);
const removeConfirmOpen = ref(false);

function selectedLocalFor(group: SeriesGroup): number[] {
  return group.galleries
    .filter((member) => member.is_local && member.gallery_id && localSelection.value.has(member.gallery_id))
    .map((member) => member.gallery_id as number);
}

function selectedCloudFor(group: SeriesGroup): number[] {
  return group.galleries
    .filter((member) => !member.is_local && member.gid && cloudSelection.value.has(member.gid))
    .map((member) => member.gid as number);
}

function openRemove(group: SeriesGroup): void {
  const local = selectedLocalFor(group);
  const cloud = selectedCloudFor(group);
  removeTargetId.value = group.id;
  removeTargetsLocal.value = local;
  removeTargetsCloud.value = cloud;
  removeGids.value = "";
  removeError.value = "";
  if (local.length || cloud.length) {
    removeConfirmOpen.value = true;
  } else {
    removeOpen.value = true;
  }
}

async function removeItems(seriesId: number, local: number[], cloud: number[]): Promise<void> {
  busy.value = true;
  removeError.value = "";
  try {
    if (local.length) await removeSeriesItems(seriesId, local);
    if (cloud.length) await removeSeriesCloudItems(seriesId, cloud);
    ui.success(t("seriesPage.removed", { count: local.length + cloud.length }));
    for (const id of local) localSelection.value.delete(id);
    for (const gid of cloud) cloudSelection.value.delete(gid);
    localSelection.value = new Set(localSelection.value);
    cloudSelection.value = new Map(cloudSelection.value);
    removeConfirmOpen.value = false;
    removeOpen.value = false;
    await load();
  } catch (cause) {
    removeError.value = message(cause);
  } finally {
    busy.value = false;
  }
}

async function confirmRemoveSelected(): Promise<void> {
  const target = removeTargetId.value;
  if (target === null) return;
  await removeItems(target, removeTargetsLocal.value, removeTargetsCloud.value);
}

async function submitManualRemove(): Promise<void> {
  const target = removeTargetId.value;
  if (target === null || busy.value) return;
  const gids = parseGids(removeGids.value);
  if (!gids.length) {
    removeError.value = t("seriesPage.removeEmpty");
    return;
  }
  const group = groups.value.find((item) => item.id === target);
  const local: number[] = [];
  const cloud: number[] = [];
  for (const gid of gids) {
    const member = group?.galleries.find((item) => item.gid === gid);
    if (member?.is_local && member.gallery_id) local.push(member.gallery_id);
    else cloud.push(gid);
  }
  await removeItems(target, local, cloud);
}

/* ---------------------------------------------------------------- downloads */

async function downloadSelection(original: boolean): Promise<void> {
  if (busy.value) return;
  if (!selectedCount.value) {
    ui.info(t("seriesPage.downloadEmpty"));
    return;
  }
  busy.value = true;
  let queued = 0;
  let skipped = 0;
  try {
    const cloudByFavcat = new Map<number, number[]>();
    for (const [gid, favcat] of cloudSelection.value.entries()) {
      const category = favcat ?? 0;
      const bucket = cloudByFavcat.get(category) ?? [];
      bucket.push(gid);
      cloudByFavcat.set(category, bucket);
    }
    for (const [favcat, gids] of cloudByFavcat.entries()) {
      const result = await downloadSelectedFavorites(
        favcat,
        gids,
        original ? { quality: "original" } : {},
      );
      queued += result.queued ?? 0;
      skipped += result.skipped ?? 0;
    }
    for (const id of localSelection.value) {
      try {
        if (original) await downloadGalleryOriginal(id, false);
        else await redownloadGallery(id);
        queued += 1;
      } catch {
        skipped += 1;
      }
    }
    ui.success(t("seriesPage.downloadQueued", { count: queued }));
    if (skipped) ui.info(t("seriesPage.downloadSkipped", { count: skipped }));
    clearSelection();
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="series" data-testid="series-view">
    <header class="series__header">
      <p class="series__eyebrow">{{ t("seriesPage.eyebrow") }}</p>
      <h1 class="series__title">{{ t("seriesPage.title") }}</h1>
      <p class="series__subtitle">{{ t("seriesPage.subtitle") }}</p>
    </header>

    <div class="series__toolbar">
      <Button variant="filled" data-testid="series-create" @click="openCreate">
        {{ t("seriesPage.create") }}
      </Button>
      <Button
        variant="outlined"
        :loading="busy"
        data-testid="series-rebuild"
        @click="rebuild"
      >
        {{ t("seriesPage.rebuild") }}
      </Button>
      <Button
        :variant="showAll ? 'tonal' : 'outlined'"
        data-testid="series-show-all"
        @click="toggleShowAll"
      >
        {{ showAll ? "✓ " : "" }}{{ t("seriesPage.showAll") }}
      </Button>
      <Button
        variant="outlined"
        :disabled="!selectedCount"
        data-testid="series-download"
        @click="downloadSelection(false)"
      >
        {{ t("seriesPage.download") }}
      </Button>
      <Button
        variant="outlined"
        :disabled="!selectedCount"
        data-testid="series-download-original"
        @click="downloadSelection(true)"
      >
        {{ t("seriesPage.downloadOriginal") }}
      </Button>
      <span class="series__stats" data-testid="series-stats">
        {{
          t("seriesPage.stats", {
            groups: total,
            items: totalItems,
          })
        }}
      </span>
    </div>

    <div class="series__selection" data-testid="series-selection">
      <span>{{ t("seriesPage.selectedCount", { count: selectedCount }) }}</span>
      <Button
        variant="text"
        size="compact"
        :disabled="!selectedCount"
        data-testid="series-clear-selection"
        @click="clearSelection"
      >
        {{ t("seriesPage.clearSelection") }}
      </Button>
    </div>

    <div class="series__pager">
      <Button
        variant="text"
        size="compact"
        :disabled="page <= 1"
        data-testid="series-prev"
        @click="goPage(page - 1)"
      >
        ←
      </Button>
      <span data-testid="series-page-info">
        {{ t("seriesPage.page", { page, pages: totalPages }) }}
      </span>
      <Button
        variant="text"
        size="compact"
        :disabled="page >= totalPages"
        data-testid="series-next"
        @click="goPage(page + 1)"
      >
        →
      </Button>
    </div>

    <div v-if="loading" class="series__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 4" :key="index" variant="line" :lines="4" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('seriesPage.loadFailed')"
      :body="error"
      :retry-label="t('seriesPage.retry')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!groups.length"
      :title="t('seriesPage.empty')"
      :body="t('seriesPage.subtitle')"
      testid="series-empty"
    />

    <div v-else class="series__list">
      <section
        v-for="group in groups"
        :key="group.id"
        class="group"
        :data-series-id="group.id"
        data-testid="series-group"
      >
        <header class="group__head">
          <div class="group__title-wrap">
            <h2 class="group__title">{{ group.name }}</h2>
            <span class="group__count">{{ group.count ?? group.galleries.length }}</span>
            <span class="group__badge">
              {{ group.match_key ? t("seriesPage.auto") : t("seriesPage.manual") }}
            </span>
          </div>
          <div class="group__actions">
            <Button
              variant="outlined"
              size="compact"
              data-testid="series-add-item"
              @click="openAdd(group)"
            >
              {{ t("seriesPage.addItem") }}
            </Button>
            <Button
              variant="outlined"
              size="compact"
              data-testid="series-remove-item"
              @click="openRemove(group)"
            >
              {{ t("seriesPage.removeItem") }}
            </Button>
            <Button
              variant="outlined"
              size="compact"
              data-testid="series-rename"
              @click="openRename(group)"
            >
              {{ t("seriesPage.rename") }}
            </Button>
            <Button
              variant="text"
              size="compact"
              data-testid="series-delete"
              @click="openDelete(group)"
            >
              {{ t("seriesPage.delete") }}
            </Button>
          </div>
        </header>

        <div v-if="group.galleries.length" class="group__grid">
          <SeriesMemberCard
            v-for="member in group.galleries"
            :key="member.gallery_id ?? member.gid ?? 0"
            :member="member"
            :selected="isSelected(member)"
            @toggle="toggleMember"
          />
        </div>
        <p v-else class="group__empty">{{ t("legacy.noGalleries") }}</p>
      </section>
    </div>

    <!-- create / rename -->
    <Dialog
      :open="nameDialogOpen"
      :title="nameDialogMode === 'create' ? t('seriesPage.createTitle') : t('seriesPage.renameTitle')"
      testid="series-name-dialog"
      @close="nameDialogOpen = false"
    >
      <div class="series__form">
        <Input
          v-model="nameValue"
          :label="t('seriesPage.nameLabel')"
          :placeholder="t('seriesPage.namePlaceholder')"
          :error="nameError"
          data-testid="series-name-input"
          @enter="submitName"
        />
      </div>
      <template #footer>
        <Button variant="text" @click="nameDialogOpen = false">
          {{ t("seriesPage.cancel") }}
        </Button>
        <Button
          :disabled="!nameValue.trim() || busy"
          :loading="busy"
          data-testid="series-name-submit"
          @click="submitName"
        >
          {{ t("seriesPage.save") }}
        </Button>
      </template>
    </Dialog>

    <!-- delete -->
    <Dialog
      :open="deleteOpen"
      :title="t('seriesPage.delete')"
      testid="series-delete-dialog"
      @close="deleteOpen = false"
    >
      <p class="series__hint">{{ t("seriesPage.confirmDelete") }}</p>
      <template #footer>
        <Button variant="text" @click="deleteOpen = false">
          {{ t("seriesPage.cancel") }}
        </Button>
        <Button variant="filled" :loading="busy" data-testid="series-delete-confirm" @click="confirmDelete">
          {{ t("seriesPage.confirm") }}
        </Button>
      </template>
    </Dialog>

    <!-- add items -->
    <Dialog
      :open="addOpen"
      :title="t('seriesPage.addTitle')"
      testid="series-add-dialog"
      @close="addOpen = false"
    >
      <div class="series__form">
        <Input
          v-model="manualGids"
          :label="t('seriesPage.manualGids')"
          :helper="t('seriesPage.manualGidsHint')"
          placeholder="123456, 789012"
          data-testid="series-manual-gids"
        />
        <div class="series__candidate-search">
          <Input
            v-model="candidateQuery"
            :label="t('seriesPage.candidates')"
            :placeholder="t('seriesPage.candidatesSearch')"
            @enter="loadCandidates"
          />
          <Button variant="outlined" data-testid="series-candidate-search" @click="loadCandidates">
            {{ t("legacy.search") }}
          </Button>
        </div>
        <div class="series__candidates" data-testid="series-candidates">
          <p v-if="candidatesLoading" class="series__hint">{{ t("legacy.loading") }}</p>
          <p v-else-if="!candidates.length" class="series__hint">
            {{ t("seriesPage.noCandidates") }}
          </p>
          <label
            v-for="candidate in candidates"
            :key="candidate.gid"
            class="candidate"
          >
            <input
              type="checkbox"
              :checked="candidateSelection.has(candidate.gid)"
              @change="toggleCandidate(candidate.gid, ($event.target as HTMLInputElement).checked)"
            />
            <img
              v-if="candidate.thumb"
              class="candidate__thumb"
              :src="candidate.thumb"
              alt=""
              loading="lazy"
            />
            <span class="candidate__title">{{ candidate.title || `gid ${candidate.gid}` }}</span>
            <span class="candidate__gid">gid: {{ candidate.gid }}</span>
          </label>
        </div>
        <p v-if="addError" class="series__error">{{ addError }}</p>
      </div>
      <template #footer>
        <Button variant="text" @click="addOpen = false">
          {{ t("seriesPage.cancel") }}
        </Button>
        <Button :disabled="busy" :loading="busy" data-testid="series-add-submit" @click="submitAdd">
          {{ t("seriesPage.confirm") }}
        </Button>
      </template>
    </Dialog>

    <!-- remove selected confirmation -->
    <Dialog
      :open="removeConfirmOpen"
      :title="t('seriesPage.removeTitle')"
      testid="series-remove-dialog"
      @close="removeConfirmOpen = false"
    >
      <p class="series__hint">{{ t("seriesPage.removeConfirm") }}</p>
      <p class="series__hint">
        {{ t("seriesPage.selectedCount", { count: removeTargetsLocal.length + removeTargetsCloud.length }) }}
      </p>
      <p v-if="removeError" class="series__error">{{ removeError }}</p>
      <template #footer>
        <Button variant="text" @click="removeConfirmOpen = false">
          {{ t("seriesPage.cancel") }}
        </Button>
        <Button
          variant="filled"
          :loading="busy"
          data-testid="series-remove-confirm"
          @click="confirmRemoveSelected"
        >
          {{ t("seriesPage.confirm") }}
        </Button>
      </template>
    </Dialog>

    <!-- manual remove -->
    <Dialog
      :open="removeOpen"
      :title="t('seriesPage.removeTitle')"
      testid="series-remove-manual-dialog"
      @close="removeOpen = false"
    >
      <div class="series__form">
        <p class="series__hint">{{ t("seriesPage.removeHint") }}</p>
        <Input
          v-model="removeGids"
          :label="t('seriesPage.removeGids')"
          :error="removeError"
          placeholder="123456, 789012"
          data-testid="series-remove-gids"
          @enter="submitManualRemove"
        />
      </div>
      <template #footer>
        <Button variant="text" @click="removeOpen = false">
          {{ t("seriesPage.cancel") }}
        </Button>
        <Button
          variant="filled"
          :disabled="busy"
          :loading="busy"
          data-testid="series-remove-submit"
          @click="submitManualRemove"
        >
          {{ t("seriesPage.confirm") }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.series {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.series__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.series__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.series__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.series__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.series__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.series__stats {
  margin-left: auto;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.series__selection {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.series__pager {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.series__skeletons {
  display: grid;
  gap: var(--gv-space-3);
}

.series__list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
}

.group__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
  padding-bottom: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.group__title-wrap {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
  min-width: 0;
}

.group__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
  overflow-wrap: anywhere;
}

.group__count,
.group__badge {
  height: 20px;
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  line-height: 20px;
}

.group__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.group__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: var(--gv-space-2);
}

.group__empty {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.series__form {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.series__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.series__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.series__candidate-search {
  display: flex;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.series__candidates {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  max-height: 220px;
  overflow-y: auto;
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-lowest);
}

.candidate {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  padding: var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  cursor: pointer;
}

.candidate:hover {
  background: var(--gv-color-surface-container-highest);
}

.candidate input {
  width: 18px;
  height: 18px;
  accent-color: var(--gv-color-primary);
}

.candidate__thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
}

.candidate__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate__gid {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}
</style>
