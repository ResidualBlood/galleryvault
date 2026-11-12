<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Input from "@/components/ui/Input.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import { ApiError } from "@/api/client";
import { fetchTagFacets, type TagSuggestion } from "@/api/library";
import {
  fetchTags,
  isCjkQuery,
  reloadTags,
  startTagSync,
} from "@/api/tags";
import { useUiStore } from "@/stores/ui";
import { ensureTagsMessages } from "./messages";

ensureTagsMessages();

const { t, te } = useI18n();
const route = useRoute();
const router = useRouter();
const ui = useUiStore();

const items = ref<TagSuggestion[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(100);
const facets = ref<Record<string, number>>({});
const facetTotal = ref(0);
const q = ref("");
const namespace = ref("");
const loading = ref(true);
const error = ref("");
const reloadBusy = ref(false);
const syncBusy = ref(false);

let controller: AbortController | null = null;

const cjk = computed(() => isCjkQuery(q.value.trim()));
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const maxUsage = computed(() =>
  items.value.reduce((max, item) => Math.max(max, item.usage_count ?? 0), 0),
);

function namespaceLabel(value: string): string {
  const key = `legacy.ns.${value}`;
  return te(key) ? t(key) : value;
}

const namespacePills = computed(() => {
  const entries = Object.entries(facets.value).sort((a, b) => b[1] - a[1]);
  return [
    { value: "", label: t("tagsPage.allNamespaces"), count: facetTotal.value },
    ...entries.map(([value, count]) => ({ value, label: namespaceLabel(value), count })),
  ];
});

function message(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof Error) return cause.message;
  return String(cause);
}

function first(value: unknown): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value === null || value === undefined ? "" : String(value);
}

async function loadFacets(): Promise<void> {
  try {
    const data = await fetchTagFacets();
    const counts: Record<string, number> = {};
    for (const facet of data.facets ?? []) {
      if (facet.namespace) counts[facet.namespace] = facet.total;
    }
    facets.value = counts;
    facetTotal.value = Object.values(counts).reduce((sum, value) => sum + value, 0);
  } catch {
    facets.value = {};
    facetTotal.value = 0;
  }
}

async function load(): Promise<void> {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  q.value = first(route.query.q);
  namespace.value = first(route.query.ns);
  page.value = Math.max(1, Number.parseInt(first(route.query.page) || "1", 10) || 1);
  try {
    const data = await fetchTags(
      { q: q.value, namespace: namespace.value, page: page.value, page_size: pageSize.value },
      controller.signal,
    );
    let rows = data.items ?? [];
    if (isCjkQuery(q.value) && q.value) {
      rows = rows.filter((item) => item.usage_count > 0);
      if (namespace.value) rows = rows.filter((item) => item.namespace === namespace.value);
    }
    items.value = rows;
    total.value = data.total ?? rows.length;
    pageSize.value = data.page_size || pageSize.value;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") return;
    error.value = message(cause);
    items.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function query(patch: Record<string, string> = {}): Record<string, string> {
  const merged: Record<string, string> = {
    q: q.value.trim(),
    ns: namespace.value,
    ...patch,
  };
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(merged)) if (value) out[key] = value;
  return out;
}

function selectNamespace(value: string): void {
  void router.push({ name: "tags", query: query({ ns: value, page: "" }) });
}

function search(): void {
  void router.push({ name: "tags", query: query({ page: "" }) });
}

function goPage(target: number): void {
  if (cjk.value) return;
  const next = Math.min(totalPages.value, Math.max(1, target));
  void router.push({ name: "tags", query: query({ page: next > 1 ? String(next) : "" }) });
}

function tagKey(tag: TagSuggestion): string {
  return tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name;
}

function sizeClass(usage: number): string {
  const max = maxUsage.value;
  if (max <= 0) return "cloud-tag--s1";
  const ratio = usage / max;
  if (ratio >= 0.75) return "cloud-tag--s4";
  if (ratio >= 0.45) return "cloud-tag--s3";
  if (ratio >= 0.2) return "cloud-tag--s2";
  return "cloud-tag--s1";
}

async function reload(): Promise<void> {
  if (reloadBusy.value) return;
  reloadBusy.value = true;
  try {
    const result = await reloadTags();
    if (result.ok) {
      ui.success(t("tagsPage.reloadOk"));
      await loadFacets();
      await load();
    } else {
      ui.error(result.last_error || t("tagsPage.reloadFailed"));
    }
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    reloadBusy.value = false;
  }
}

async function syncAll(): Promise<void> {
  if (syncBusy.value) return;
  syncBusy.value = true;
  try {
    const result = await startTagSync();
    if (result.status === "paused") {
      ui.info(t("tagsPage.syncPaused"));
    } else {
      ui.success(t("tagsPage.syncQueued"));
    }
  } catch (cause) {
    ui.error(message(cause));
  } finally {
    syncBusy.value = false;
  }
}

watch(
  () => route.query,
  () => {
    void load();
  },
);

onBeforeUnmount(() => {
  controller?.abort();
});

void loadFacets();
void load();
</script>

<template>
  <section class="tags" data-testid="tags-view">
    <header class="tags__header">
      <p class="tags__eyebrow">{{ t("tagsPage.eyebrow") }}</p>
      <h1 class="tags__title">{{ t("tagsPage.title") }}</h1>
      <p class="tags__subtitle">{{ t("tagsPage.subtitle") }}</p>
    </header>

    <div class="tags__toolbar">
      <form class="tags__search" role="search" @submit.prevent="search">
        <Input
          v-model="q"
          :label="t('tagsPage.search')"
          :placeholder="t('tagsPage.searchPlaceholder')"
          data-testid="tags-search-input"
          @enter="search"
        />
        <Button type="submit" variant="filled" data-testid="tags-search-submit">
          {{ t("tagsPage.search") }}
        </Button>
      </form>
      <Button
        variant="outlined"
        :loading="reloadBusy"
        data-testid="tags-reload"
        :title="t('tagsPage.reloadHint')"
        @click="reload"
      >
        {{ reloadBusy ? t("tagsPage.reloading") : t("tagsPage.reload") }}
      </Button>
      <Button
        variant="outlined"
        :loading="syncBusy"
        data-testid="tags-sync"
        :title="t('tagsPage.syncHint')"
        @click="syncAll"
      >
        {{ t("tagsPage.syncAll") }}
      </Button>
    </div>

    <div class="tags__pills" :aria-label="t('tagsPage.title')">
      <button
        v-for="pill in namespacePills"
        :key="pill.value || 'all'"
        type="button"
        class="pill"
        :class="{ 'pill--active': namespace === pill.value }"
        :data-testid="`tags-ns-${pill.value || 'all'}`"
        @click="selectNamespace(pill.value)"
      >
        {{ pill.label }} <b>{{ pill.count }}</b>
      </button>
    </div>

    <p v-if="namespace" class="tags__current" data-testid="tags-current-ns">
      {{ t("tagsPage.currentNamespace", { namespace }) }}
      <RouterLink class="tags__link" :to="{ name: 'tags', query: query({ ns: '', page: '' }) }">
        {{ t("tagsPage.backToAll") }}
      </RouterLink>
    </p>

    <div v-if="loading" class="tags__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 6" :key="index" variant="line" :lines="2" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('tagsPage.loadFailed')"
      :body="error"
      :retry-label="t('tagsPage.search')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!items.length"
      :title="t('tagsPage.empty')"
      :body="t('tagsPage.subtitle')"
      testid="tags-empty"
    />

    <div v-else class="tags__cloud" data-testid="tags-cloud">
      <RouterLink
        v-for="tag in items"
        :key="tagKey(tag)"
        class="cloud-tag"
        :class="[sizeClass(tag.usage_count), tag.namespace ? `cloud-tag--${tag.namespace}` : '']"
        :to="{ name: 'library', query: { tags: tagKey(tag) } }"
        :title="tag.namespace ? `${tag.namespace}:${tag.name}` : tag.name"
      >
        <span class="cloud-tag__ns" v-if="tag.namespace">{{ tag.namespace }}:</span>
        <span class="cloud-tag__name">{{ tag.display || tag.name }}</span>
        <small class="cloud-tag__count">{{ tag.usage_count }}</small>
      </RouterLink>
    </div>

    <div v-if="!loading && !error && items.length" class="tags__pager">
      <p v-if="cjk" class="tags__hint">{{ t("tagsPage.cjkHint") }}</p>
      <template v-else>
        <Button
          variant="text"
          size="compact"
          :disabled="page <= 1"
          data-testid="tags-prev"
          @click="goPage(page - 1)"
        >
          {{ t("tagsPage.prev") }}
        </Button>
        <span data-testid="tags-page-info">
          {{ t("tagsPage.pageInfo", { page, pages: totalPages }) }}
        </span>
        <Button
          variant="text"
          size="compact"
          :disabled="page >= totalPages"
          data-testid="tags-next"
          @click="goPage(page + 1)"
        >
          {{ t("tagsPage.next") }}
        </Button>
      </template>
    </div>
  </section>
</template>

<style scoped>
.tags {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.tags__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.tags__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.tags__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.tags__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.tags__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
}

.tags__search {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--gv-space-2);
  flex: 1;
  min-width: 260px;
}

.tags__pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: 28px;
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.pill:hover {
  background: var(--gv-color-surface-container-highest);
}

.pill--active {
  border-color: var(--gv-color-primary);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.pill b {
  font: var(--gv-type-label-small);
  color: inherit;
}

.tags__current {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tags__link {
  color: var(--gv-color-primary-text);
  text-decoration: none;
}

.tags__link:hover {
  text-decoration: underline;
}

.tags__skeletons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--gv-space-2);
}

.tags__cloud {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  align-items: center;
}

.cloud-tag {
  display: inline-flex;
  align-items: baseline;
  gap: var(--gv-space-1);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  text-decoration: none;
  line-height: 28px;
}

.cloud-tag:hover {
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface);
}

.cloud-tag--s1 {
  font: var(--gv-type-label-small);
}

.cloud-tag--s2 {
  font: var(--gv-type-body-small);
}

.cloud-tag--s3 {
  font: var(--gv-type-body-medium);
}

.cloud-tag--s4 {
  font: var(--gv-type-title-small);
}

.cloud-tag__ns {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
}

.cloud-tag__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.tags__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tags__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
