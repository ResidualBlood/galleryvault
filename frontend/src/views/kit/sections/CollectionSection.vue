<script setup lang="ts">
/**
 * Collection specimen (`#/_kit`).
 *
 * Three swap-able views over the same static data: the grid card with hover
 * tag layer, the list row with inline tags and the table with a sticky header
 * and sortable columns. Data is static so the kit never touches the backend.
 */
import { ref } from "vue";
import GalleryCollection from "@/components/gallery/GalleryCollection.vue";
import ViewModeToggle from "@/components/gallery/ViewModeToggle.vue";
import {
  BROWSE_TABLE_COLUMNS,
  type SortState,
} from "@/components/gallery/table-columns";
import type { ViewMode } from "@/composables/useViewMode";
import type { GalleryItem } from "@/api/library";

const mode = ref<ViewMode>("grid");
const sort = ref<SortState | null>(null);

const categories = ["doujinshi", "manga", "artistcg", "gamecg", "western", "non-h"];

const items: GalleryItem[] = Array.from({ length: 24 }, (_, index) => {
  const id = index + 1;
  return {
    id,
    gid: 9000 + id,
    token: `kit-${id}`,
    title: `Specimen gallery ${id} — a title long enough to clamp at two lines`,
    category: categories[index % categories.length],
    page_count: 24 + index * 7,
    cover_url: null,
    tags: [
      { namespace: "language", name: "chinese", display: "中文" },
      { namespace: "female", name: "big breasts", display: "巨乳" },
      { namespace: "artist", name: "sample artist", display: "示例作者" },
      { namespace: "male", name: "sole male", display: "单男" },
      { namespace: "other", name: "full color", display: "全彩" },
    ],
    tag_count: 5,
    uploader: `uploader-${index % 6}`,
    posted_at: new Date(Date.UTC(2025, 0, 1 + index)).toISOString(),
    file_size: 1024 * 1024 * (12 + index),
    rating: 1 + (index % 9) / 2,
    favorite: index % 4 === 0,
    reading_progress: index % 3 === 0 ? 4 : 0,
  };
});

function onSort(column: { key: string; sortKey?: string }, direction: "asc" | "desc"): void {
  if (!column.sortKey) return;
  sort.value = { key: column.key, direction };
}
</script>

<template>
  <section class="collection-section" data-testid="kit-collection">
    <header class="collection-section__head">
      <h2 class="collection-section__title">Gallery collection</h2>
      <p class="collection-section__lede">
        Grid cards keep tags in a hover / focus overlay, list rows show four tags + N and
        the table shows three + N with a sticky sortable header.
      </p>
    </header>

    <div class="collection-section__controls" data-gv-toolbar>
      <ViewModeToggle v-model="mode" />
      <span class="collection-section__mode">mode: {{ mode }}</span>
    </div>

    <GalleryCollection
      :items="items"
      :mode="mode"
      :columns="BROWSE_TABLE_COLUMNS"
      :sort="sort"
      testid="kit-collection-grid"
      @sort="onSort"
    />
  </section>
</template>

<style scoped>
.collection-section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  width: 100%;
  min-width: 0;
}

.collection-section__head {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.collection-section__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.collection-section__lede {
  max-width: 72ch;
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.collection-section__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-3);
}

.collection-section__mode {
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface-variant);
}
</style>
