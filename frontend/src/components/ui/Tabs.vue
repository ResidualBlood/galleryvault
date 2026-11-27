<script lang="ts">
export interface TabItem {
  value: string;
  label: string;
  icon?: import("@/components/icons/registry").IconName;
  disabled?: boolean;
  /** Route target. When set the tab renders as a router link. */
  to?: string;
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import Icon from "@/components/icons/Icon.vue";

const props = withDefaults(
  defineProps<{
    items: TabItem[];
    /** Active value; falls back to `active` for router mode. */
    modelValue?: string;
    active?: string;
    label: string;
    testid?: string;
  }>(),
  { modelValue: "", active: "", testid: "gv-tabs" },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
}>();

const activeValue = computed(() => props.modelValue || props.active);

function select(item: TabItem, event?: MouseEvent): void {
  if (item.disabled) {
    event?.preventDefault();
    return;
  }
  emit("update:modelValue", item.value);
  emit("change", item.value);
}

function onKeydown(event: KeyboardEvent): void {
  const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
  if (!keys.includes(event.key)) return;
  const target = event.target as HTMLElement;
  const tabs = [
    ...((event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>(
      '[role="tab"]:not([aria-disabled="true"])',
    ) ?? []),
  ];
  const current = tabs.findIndex((tab) => tab.dataset.tabValue === target.dataset.tabValue);
  if (current < 0) return;
  event.preventDefault();
  let next = current;
  if (event.key === "Home") next = 0;
  else if (event.key === "End") next = tabs.length - 1;
  else if (event.key === "ArrowLeft") next = current <= 0 ? tabs.length - 1 : current - 1;
  else next = current >= tabs.length - 1 ? 0 : current + 1;
  const tab = tabs[next];
  const item = props.items.find((entry) => entry.value === tab.dataset.tabValue);
  if (!item) return;
  select(item);
  tab.focus();
}
</script>

<template>
  <div class="tabs" role="tablist" :aria-label="label" :data-testid="testid" @keydown="onKeydown">
    <component
      :is="item.to ? RouterLink : 'button'"
      v-for="item in items"
      :key="item.value"
      class="tabs__item"
      :class="{ 'tabs__item--active': item.value === activeValue }"
      :type="item.to ? undefined : 'button'"
      :to="item.to"
      role="tab"
      :aria-selected="item.value === activeValue"
      :aria-disabled="item.disabled || undefined"
      :tabindex="item.value === activeValue ? 0 : -1"
      :data-tab-value="item.value"
      @click="select(item, $event)"
    >
      <Icon v-if="item.icon" :name="item.icon" size="dense" />
      <span>{{ item.label }}</span>
    </component>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  min-width: 0;
  overflow-x: auto;
  border-bottom: 1px solid var(--gv-color-outline-variant);
  scrollbar-width: none;
}

.tabs::-webkit-scrollbar {
  display: none;
}

.tabs__item {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-control-md);
  padding: 0 var(--gv-space-3);
  border: 0;
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
}

.tabs__item::after {
  content: "";
  position: absolute;
  right: var(--gv-space-2);
  bottom: -1px;
  left: var(--gv-space-2);
  height: var(--gv-state-focus-ring-width);
  border-radius: var(--gv-radius-full);
  background: transparent;
  transition: background-color var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.tabs__item:hover {
  color: var(--gv-color-on-surface);
}

.tabs__item--active {
  color: var(--gv-color-primary-text);
}

.tabs__item--active::after {
  background: var(--gv-color-primary);
}

.tabs__item:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
  border-radius: var(--gv-radius-sm);
}

.tabs__item[aria-disabled="true"] {
  opacity: var(--gv-state-disabled);
  cursor: not-allowed;
}
</style>
