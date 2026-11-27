<script setup lang="ts">
/**
 * Single entry point for a gallery collection (PLAN polish §P5).
 *
 * Pages hand over `items`, the current `mode`, the table columns and the
 * selection / sort state; GalleryCollection renders either the grid/list
 * window or the table window and forwards the `card`, `row` and `actions`
 * slots. New list pages should only touch this component.
 */
import VirtualGrid from "./VirtualGrid.vue";
import type { SortState, TableColumn } from "./table-columns";
import type { ViewMode } from "@/composables/useViewMode";
import type { GalleryItem } from "@/api/library";

withDefaults(
  defineProps<{
    items: GalleryItem[];
    mode: ViewMode;
    columns?: readonly TableColumn[];
    source?: "local" | "online";
    sort?: SortState | null;
    selectable?: boolean;
    selected?: number[];
    loading?: boolean;
    hasMore?: boolean;
    error?: string | null;
    failures?: number;
    total?: number;
    testid?: string;
  }>(),
  {
    columns: () => [],
    source: "local",
    sort: null,
    selectable: false,
    selected: () => [],
    loading: false,
    hasMore: false,
    error: null,
    failures: 0,
    total: 0,
    testid: "gallery-collection",
  },
);

const emit = defineEmits<{
  loadMore: [];
  retry: [];
  sort: [column: TableColumn, direction: "asc" | "desc"];
  select: [id: number, selected: boolean];
  open: [item: GalleryItem];
}>();
</script>

<template>
  <VirtualGrid
    :items="items"
    :variant="mode"
    :columns="columns"
    :source="source"
    :sort="sort"
    :selectable="selectable"
    :selected="selected"
    :loading="loading"
    :has-more="hasMore"
    :error="error"
    :failures="failures"
    :total="total"
    :testid="testid"
    :data-mode="mode"
    @load-more="emit('loadMore')"
    @retry="emit('retry')"
    @sort="(column, direction) => emit('sort', column, direction)"
    @select="(id, next) => emit('select', id, next)"
    @open="(item) => emit('open', item)"
  >
    <template v-if="$slots.card" #card="slotProps">
      <slot name="card" v-bind="slotProps" />
    </template>
    <template v-if="$slots.row" #row="slotProps">
      <slot name="row" v-bind="slotProps" />
    </template>
    <template v-if="$slots.actions" #actions="slotProps">
      <slot name="actions" v-bind="slotProps" />
    </template>
  </VirtualGrid>
</template>
