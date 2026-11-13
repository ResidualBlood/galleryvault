<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Chip from "@/components/ui/Chip.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Icon from "@/components/icons/Icon.vue";
import Input from "@/components/ui/Input.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import TagChip from "@/components/tags/TagChip.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import {
  namespaceLabel,
  tagKey,
  type TagLike,
  type TagMenuEvent,
} from "@/components/tags/tag-utils";
import { useTagNavigation } from "@/components/tags/useTagNavigation";
import "@/components/tags/i18n";
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

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const tagNav = useTagNavigation("local");

const PAGE_SIZES = [50, 100, 200];

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
const menu = ref<TagMenuEvent | null>(null);

let controller: AbortController | null = null;

const cjk = computed(() => isCjkQuery(q.value.trim()));
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const headerCount = computed(() =>
  namespace.value || q.value.trim() ? total.value : facetTotal.value || total.value,
);

/** Facet counts decide the namespace order; items decide the page content. */
const groups = computed(() => {
  const order = Object.entries(facets.value)
    .sort((a, b) => b[1] - a[1])
    .map(([value]) => value);
  const rank = (value: string): number => {
    const index = order.indexOf(value);
    return index < 0 ? order.length + 1 : index;
  };

  const buckets = new Map<string, TagSuggestion[]>();
  for (const tag of items.value) {
    const key = (tag.namespace || "misc").trim() || "misc";
    const bucket = buckets.get(key);
    if (bucket) bucket.push(tag);
    else buckets.set(key, [tag]);
  }

  return [...buckets.keys()]
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map((key) => ({
      namespace: key,
      label: namespaceLabel(key, t),
      count: facets.value[key] ?? buckets.get(key)?.length ?? 0,
      items: buckets.get(key) ?? [],
    }));
});

const namespacePills = computed(() => {
  const entries = Object.entries(facets.value).sort((a, b) => b[1] - a[1]);
  return [
    {
      value: "",
      label: t("tagsPage.allNamespaces"),
      title: t("tagsPage.allNamespaces"),
      count: facetTotal.value,
    },
    ...entries.map(([value, count]) => ({
      value,
      label: namespaceLabel(value, t),
      title: `${namespaceLabel(value, t)}（${value}）`,
      count,
    })),
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
      {
        q: q.value,
        namespace: namespace.value,
        page: page.value,
        page_size: pageSize.value,
      },
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

function onPageSize(value: number): void {
  pageSize.value = value;
  void router.push({ name: "tags", query: query({ page: "" }) });
}

function onTagSelect(tag: TagLike): void {
  void tagNav.navigate(tag);
}

function onTagExclude(tag: TagLike): void {
  void tagNav.navigate(tag, { exclude: true });
}

function openTagMenu(event: TagMenuEvent): void {
  menu.value = event;
}

function onCopied(): void {
  ui.success(t("tagsUi.copied"));
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
    <PageHeader
      :title="t('tagsPage.title')"
      :count="headerCount"
      :subtitle="t('tagsPage.subtitle')"
      testid="tags-header"
    />

    <Toolbar class="tags__toolbar" size="lg" testid="tags-toolbar">
      <form class="tags__search" role="search" @submit.prevent="search">
        <Input
          v-model="q"
          class="tags__search-input"
          icon="search"
          :aria-label="t('tagsPage.search')"
          :placeholder="t('tagsPage.searchPlaceholder')"
          data-testid="tags-search-input"
          @enter="search"
        />
        <Button type="submit" variant="filled" data-testid="tags-search-submit">
          {{ t("tagsPage.search") }}
        </Button>
      </form>
      <ToolbarGroup class="tags__maint" end>
        <Button
          variant="outlined"
          icon="retry"
          :loading="reloadBusy"
          data-testid="tags-reload"
          :title="t('tagsPage.reloadHint')"
          @click="reload"
        >
          {{ reloadBusy ? t("tagsPage.reloading") : t("tagsPage.reload") }}
        </Button>
        <Button
          variant="outlined"
          icon="updates"
          :loading="syncBusy"
          data-testid="tags-sync"
          :title="t('tagsPage.syncHint')"
          @click="syncAll"
        >
          {{ t("tagsPage.syncAll") }}
        </Button>
      </ToolbarGroup>
    </Toolbar>

    <div
      class="tags__namespaces"
      role="group"
      :aria-label="t('tagsPage.title')"
      data-testid="tags-namespaces"
    >
      <Chip
        v-for="pill in namespacePills"
        :key="pill.value || 'all'"
        :label="pill.label"
        :count="pill.count"
        :selected="namespace === pill.value"
        :title="pill.title"
        :testid="`tags-ns-${pill.value || 'all'}`"
        @click="selectNamespace(pill.value)"
      />
    </div>

    <p v-if="namespace" class="tags__current" data-testid="tags-current-ns">
      {{ t("tagsPage.currentNamespace", { namespace: namespaceLabel(namespace, t) }) }}
      <span class="tags__current-raw">{{ namespace }}</span>
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
      <section
        v-for="group in groups"
        :key="group.namespace"
        class="tags__group"
        :data-group="group.namespace"
      >
        <h2 class="tags__group-title">
          <Icon name="tags" size="dense" aria-hidden="true" />
          <span>{{ group.label }}</span>
          <span class="tags__group-count">{{ group.count }}</span>
        </h2>
        <div class="tags__group-chips">
          <span v-for="tag in group.items" :key="tagKey(tag)" class="tags__tag">
            <TagChip
              :tag="tag"
              :size="24"
              @select="onTagSelect"
              @exclude="onTagExclude"
              @menu="openTagMenu"
            />
            <span class="tags__usage">{{ tag.usage_count }}</span>
          </span>
        </div>
      </section>
    </div>

    <div v-if="!loading && !error && items.length" class="tags__pager">
      <p v-if="cjk" class="tags__hint">{{ t("tagsPage.cjkHint") }}</p>
      <Pager
        v-else
        :page="page"
        :total-pages="totalPages"
        :page-size="pageSize"
        :page-size-options="PAGE_SIZES"
        testid="tags-pager"
        @update:page="goPage"
        @update:page-size="onPageSize"
      />
    </div>

    <TagMenu
      v-if="menu"
      :tag="menu.tag"
      :x="menu.x"
      :y="menu.y"
      source="local"
      @close="menu = null"
      @copied="onCopied"
    />
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

.tags__search {
  display: flex;
  flex: 1 1 320px;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.tags__search-input {
  flex: 1 1 auto;
  min-width: 0;
}

.tags__namespaces {
  display: flex;
  flex-wrap: nowrap;
  gap: var(--gv-space-1);
  overflow-x: auto;
  padding: 2px;
  scrollbar-width: thin;
}

.tags__current {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tags__current-raw {
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
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
  flex-direction: column;
  gap: var(--gv-space-4);
}

.tags__group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.tags__group-title {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.tags__group-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--gv-space-5);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-small);
}

.tags__group-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.tags__tag {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  max-width: 100%;
  min-width: 0;
}

.tags__usage {
  flex: none;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  font-variant-numeric: tabular-nums;
}

.tags__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  padding: var(--gv-space-3) 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tags__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

@media (max-width: 599.98px) {
  .tags__search {
    flex: 1 1 100%;
  }

  .tags__maint {
    flex-wrap: wrap;
    width: 100%;
    margin-inline-start: 0;
  }
}
</style>
