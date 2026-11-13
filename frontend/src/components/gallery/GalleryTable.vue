<script setup lang="ts">
/**
 * Table shell for the collection view (DESIGN.md C18).
 *
 * The header is sticky below the 56px app topbar and shares one CSS grid
 * template with the virtual body rows. Column visibility is derived from the
 * *container* width, so the table never scrolls horizontally even with the
 * persistent drawer open. Sortable headers emit `sort` with the column and the
 * direction the page should map to `order_by`; `aria-sort` tracks the state.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Icon from "@/components/icons/Icon.vue";
import { ensureCollectionMessages } from "./collection-messages";
import {
  columnTemplate,
  nextSortDirection,
  sortAriaState,
  visibleColumns,
  type SortState,
  type TableColumn,
} from "./table-columns";

ensureCollectionMessages();

const props = withDefaults(
  defineProps<{
    columns: readonly TableColumn[];
    sort?: SortState | null;
    testid?: string;
  }>(),
  { sort: null, testid: "gallery-table" },
);

const emit = defineEmits<{
  sort: [column: TableColumn, direction: "asc" | "desc"];
}>();

const { t } = useI18n();

const root = ref<HTMLElement | null>(null);
const width = ref(0);
let observer: ResizeObserver | null = null;

function measure(): void {
  width.value = root.value?.clientWidth ?? 0;
}

onMounted(() => {
  measure();
  if (typeof ResizeObserver === "function" && root.value) {
    observer = new ResizeObserver(measure);
    observer.observe(root.value);
  }
  window.addEventListener("resize", measure, { passive: true });
});

onBeforeUnmount(() => {
  observer?.disconnect();
  window.removeEventListener("resize", measure);
});

const columns = computed(() => visibleColumns(props.columns, width.value));
const template = computed(() => columnTemplate(columns.value));

function label(column: TableColumn): string {
  return t(`collection.table.${column.labelKey}`);
}

function sortLabel(column: TableColumn): string {
  const state = sortAriaState(column, props.sort);
  const key = state === "ascending" ? "asc" : state === "descending" ? "desc" : "none";
  return t(`collection.sort.${key}`, { column: label(column) });
}

function onSort(column: TableColumn): void {
  if (!column.sortKey) return;
  emit("sort", column, nextSortDirection(column, props.sort));
}
</script>

<template>
  <div ref="root" class="gallery-table" :data-testid="testid">
    <div class="gallery-table__head" role="row" :style="{ gridTemplateColumns: template }">
      <template v-for="column in columns" :key="column.key">
        <div
          v-if="column.sortKey"
          class="gallery-table__cell gallery-table__cell--head"
          :class="`gallery-table__cell--${column.align}`"
          role="columnheader"
          :aria-sort="sortAriaState(column, sort)"
          :data-column="column.key"
        >
          <Button
            variant="text"
            size="sm"
            class="gallery-table__sort"
            :icon-end="
              sortAriaState(column, sort) === 'ascending'
                ? 'sort-asc'
                : sortAriaState(column, sort) === 'descending'
                  ? 'sort-desc'
                  : 'sort'
            "
            :aria-label="sortLabel(column)"
            :title="sortLabel(column)"
            @click="onSort(column)"
          >
            {{ label(column) }}
          </Button>
        </div>
        <div
          v-else
          class="gallery-table__cell gallery-table__cell--head"
          :class="`gallery-table__cell--${column.align}`"
          role="columnheader"
          :data-column="column.key"
        >
          <span v-if="column.key === 'selection'" class="gallery-table__head-spacer" aria-hidden="true">
            <Icon name="check" size="sm" />
          </span>
          <span v-else>{{ label(column) }}</span>
        </div>
      </template>
    </div>

    <div class="gallery-table__body" role="rowgroup">
      <slot :columns="columns" />
    </div>
  </div>
</template>

<style scoped>
.gallery-table {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}

.gallery-table__head {
  position: sticky;
  top: var(--gv-table-head-top, var(--gv-size-topbar));
  z-index: 6;
  display: grid;
  align-items: center;
  height: 40px;
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface);
}

.gallery-table__cell {
  display: flex;
  align-items: center;
  min-width: 0;
  padding: 0 var(--gv-space-3);
  overflow: hidden;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
  white-space: nowrap;
}

.gallery-table__cell--start {
  justify-content: flex-start;
}

.gallery-table__cell--center {
  justify-content: center;
}

.gallery-table__cell--end {
  justify-content: flex-end;
}

.gallery-table__sort {
  max-width: 100%;
}

.gallery-table__head-spacer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--gv-color-on-surface-variant);
}

.gallery-table__body {
  position: relative;
  min-width: 0;
}
</style>
