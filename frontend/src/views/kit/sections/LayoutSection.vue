<script setup lang="ts">
import { ref } from "vue";
import Button from "@/components/ui/Button.vue";
import Chip from "@/components/ui/Chip.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import FilterButton from "@/components/ui/FilterButton.vue";
import Menu, { type MenuItem } from "@/components/ui/Menu.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Pager from "@/components/ui/Pager.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import SelectionBar from "@/components/ui/SelectionBar.vue";
import Tabs from "@/components/ui/Tabs.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
import ToolbarGroup from "@/components/ui/ToolbarGroup.vue";
import Icon from "@/components/icons/Icon.vue";
import type { IconName } from "@/components/icons/registry";

const view = ref("grid");
const tab = ref("all");
const page = ref(2);
const pageSize = ref(48);
const selected = ref(2);
const filterCount = ref(3);

const viewOptions: Array<{ value: string; label: string; icon: IconName }> = [
  { value: "grid", label: "Grid", icon: "view-grid" },
  { value: "list", label: "List", icon: "view-list" },
  { value: "table", label: "Table", icon: "view-table" },
];

const tabs = [
  { value: "all", label: "All" },
  { value: "unread", label: "Unread" },
  { value: "downloaded", label: "Downloaded" },
];

const menuItems: MenuItem[] = [
  { id: "open", label: "Open", icon: "play" },
  { id: "copy", label: "Copy original", icon: "copy" },
  { id: "delete", label: "Delete", icon: "delete", danger: true, separatorBefore: true },
];

const lastAction = ref("none");

function onMenuSelect(id: string): void {
  lastAction.value = id;
}
</script>

<template>
  <section class="layout-section" aria-labelledby="kit-layout-title" data-testid="kit-layout">
    <h2 id="kit-layout-title" class="layout-section__title">Layout kit</h2>
    <p class="layout-section__note">
      Shared page skeleton: page header, grouped toolbar with compact overflow, selection bar, pager and
      empty / error states.
    </p>

    <div class="layout-section__block">
      <PageHeader
        title="Library"
        :count="128"
        subtitle="Local galleries, newest first"
        :crumbs="[{ label: 'Home', to: '/browse' }, { label: 'Library' }]"
        testid="kit-page-header"
      >
        <template #actions>
          <Button variant="outlined">Scan</Button>
          <Button variant="filled">Add library</Button>
        </template>
      </PageHeader>
    </div>

    <div class="layout-section__block">
      <h3 class="layout-section__label">Toolbar</h3>
      <Toolbar
        size="lg"
        testid="kit-layout-toolbar"
        more-testid="kit-layout-overflow"
      >
        <ToolbarGroup testid="kit-layout-primary">
          <FilterButton :count="filterCount" label="Filter" testid="kit-filter" />
          <Button variant="outlined" @click="filterCount = filterCount > 0 ? 0 : 3">
            <Icon name="sort" size="dense" />
            <span>Sort</span>
          </Button>
        </ToolbarGroup>
        <ToolbarGroup collapsible testid="kit-layout-collapsible">
          <Button variant="text">Import</Button>
          <Button variant="text">Export</Button>
        </ToolbarGroup>
        <ToolbarGroup end>
          <Button variant="filled">Refresh</Button>
        </ToolbarGroup>
      </Toolbar>
    </div>

    <div class="layout-section__block">
      <h3 class="layout-section__label">Selection</h3>
      <SelectionBar :count="selected" label="2 selected" @clear="selected = 0">
        <Button variant="outlined">Archive</Button>
        <Button variant="outlined">Add tags</Button>
        <template #danger>
          <Button class="layout-section__danger" variant="text">Delete</Button>
        </template>
      </SelectionBar>
      <Button v-if="selected === 0" variant="text" @click="selected = 2">Select two</Button>
    </div>

    <div class="layout-section__block">
      <h3 class="layout-section__label">Segments, chips and tabs</h3>
      <div class="layout-section__row">
        <SegmentedControl
          v-model="view"
          :options="viewOptions"
          label="View mode"
          testid="kit-segmented"
        />
        <Chip label="Doujinshi" :count="24" selected />
        <Chip label="Language: Chinese" variant="assist" icon="language" />
        <Chip label="Favorites" variant="filter" />
      </div>
      <Tabs v-model="tab" :items="tabs" label="Library tabs" testid="kit-tabs" />
      <Menu :items="menuItems" label="Gallery actions" testid="kit-menu" @select="onMenuSelect" />
      <p class="layout-section__value">last action: {{ lastAction }}</p>
    </div>

    <div class="layout-section__block">
      <h3 class="layout-section__label">Pager</h3>
      <p class="layout-section__value" data-testid="kit-pager-current">page {{ page }}</p>
      <Pager
        v-model:page="page"
        v-model:page-size="pageSize"
        :total-pages="12"
        :page-size-options="[24, 48, 96]"
        testid="kit-pager"
      >
        <template #date-jump>
          <Button variant="outlined" size="compact">Date</Button>
        </template>
      </Pager>
      <Pager :page="1" :total-pages="0" testid="kit-pager-open">
        <template #date-jump>
          <Button variant="outlined" size="compact">Date</Button>
        </template>
      </Pager>
    </div>

    <div class="layout-section__block">
      <h3 class="layout-section__label">States</h3>
      <div class="layout-section__states">
        <EmptyState
          icon="library"
          title="No galleries yet"
          body="Add a library folder to start browsing."
          action-label="Add library"
          secondary-label="Refresh"
          testid="kit-empty"
        />
        <ErrorState
          title="Failed to load"
          body="The server did not respond. Check the connection and retry."
          retry-label="Retry"
          testid="kit-error"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.layout-section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
}

.layout-section__title {
  margin: 0;
  font: var(--gv-type-title-large);
  color: var(--gv-color-on-surface);
}

.layout-section__note {
  margin: 0;
  max-width: 72ch;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.layout-section__block {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-low);
}

.layout-section__label {
  margin: 0;
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface-variant);
}

.layout-section__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.layout-section__value {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.layout-section__states {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--gv-space-3);
}

.layout-section__danger {
  color: var(--gv-color-error);
}

@media (max-width: 599.98px) {
  .layout-section__block {
    padding: var(--gv-space-3);
  }
}
</style>
