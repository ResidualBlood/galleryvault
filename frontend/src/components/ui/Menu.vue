<script lang="ts">
export interface MenuItem {
  id: string;
  label: string;
  icon?: import("@/components/icons/registry").IconName;
  danger?: boolean;
  disabled?: boolean;
  separatorBefore?: boolean;
}
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import type { IconName } from "@/components/icons/registry";
import Icon from "@/components/icons/Icon.vue";
import Button from "./Button.vue";
import IconButton from "./IconButton.vue";
import Popover from "./Popover.vue";
import Sheet from "./Sheet.vue";

withDefaults(
  defineProps<{
    items?: MenuItem[];
    label: string;
    icon?: IconName;
    /** Render the trigger with its text label instead of icon-only. */
    showLabel?: boolean;
    align?: "start" | "end";
    testid?: string;
  }>(),
  {
    items: () => [],
    icon: "more",
    showLabel: false,
    align: "end",
    testid: "gv-menu",
  },
);

const emit = defineEmits<{ select: [id: string] }>();

const compact = ref(false);
const sheetOpen = ref(false);
const popover = ref<InstanceType<typeof Popover> | null>(null);
const trigger = ref<HTMLElement | null>(null);
const panel = ref<HTMLElement | null>(null);
let media: MediaQueryList | null = null;

function syncCompact(event?: MediaQueryListEvent): void {
  if (event) {
    compact.value = !event.matches;
    return;
  }
  if (media) compact.value = !media.matches;
}

onMounted(() => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  media = window.matchMedia("(min-width: 600px)");
  syncCompact();
  media.addEventListener?.("change", syncCompact);
});

onBeforeUnmount(() => {
  media?.removeEventListener?.("change", syncCompact);
});

const open = computed(() =>
  compact.value ? sheetOpen.value : Boolean(popover.value?.open),
);

function focusTrigger(): void {
  trigger.value?.querySelector<HTMLElement>("button")?.focus();
}

function focusFirst(): void {
  const first = panel.value?.querySelector<HTMLElement>(
    '[role="menuitem"]:not(:disabled)',
  );
  first?.focus();
}

function openMenu(): void {
  if (compact.value) sheetOpen.value = true;
  else popover.value?.toggle();
  void nextTick(focusFirst);
}

function closeMenu(restoreFocus = false): void {
  if (compact.value) sheetOpen.value = false;
  else popover.value?.close();
  if (restoreFocus) void nextTick(focusTrigger);
}

function onTriggerClick(): void {
  void nextTick(() => {
    if (open.value) focusFirst();
  });
}

function onTriggerKeydown(event: KeyboardEvent): void {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  if (!open.value) openMenu();
  else void nextTick(focusFirst);
}

function onPanelKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault();
    closeMenu(true);
    return;
  }
  if (event.key === "Tab") {
    closeMenu();
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const items = [
    ...(panel.value?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? []),
  ];
  if (!items.length) return;
  event.preventDefault();
  const current = items.indexOf(document.activeElement as HTMLElement);
  let next = 0;
  if (event.key === "End") next = items.length - 1;
  else if (event.key === "ArrowUp") next = current <= 0 ? items.length - 1 : current - 1;
  else next = current >= items.length - 1 ? 0 : current + 1;
  items[next]?.focus();
}

function select(item: MenuItem): void {
  if (item.disabled) return;
  emit("select", item.id);
  closeMenu(true);
}
</script>

<template>
  <span ref="trigger" class="menu">
    <Popover v-if="!compact" ref="popover" :align="align">
      <template #trigger>
        <IconButton
          v-if="!showLabel"
          :label="label"
          size="small"
          :data-testid="`${testid}-trigger`"
          @keydown="onTriggerKeydown"
          @click="onTriggerClick"
        >
          <Icon :name="icon" size="dense" />
        </IconButton>
        <Button
          v-else
          variant="text"
          :data-testid="`${testid}-trigger`"
          @keydown="onTriggerKeydown"
          @click="onTriggerClick"
        >
          <Icon :name="icon" size="dense" />
          <span>{{ label }}</span>
        </Button>
      </template>
      <div ref="panel" :data-testid="`${testid}-panel`">
        <ul class="menu__list" role="none" @keydown="onPanelKeydown">
          <template v-for="item in items" :key="item.id">
            <li v-if="item.separatorBefore" class="menu__separator" role="separator" />
            <li role="none">
              <button
                class="menu__item"
                :class="{ 'menu__item--danger': item.danger }"
                type="button"
                role="menuitem"
                :disabled="item.disabled"
                @click="select(item)"
              >
                <Icon v-if="item.icon" :name="item.icon" size="dense" />
                <span>{{ item.label }}</span>
              </button>
            </li>
          </template>
        </ul>
        <slot :close="closeMenu" />
      </div>
    </Popover>

    <template v-else>
      <IconButton
        v-if="!showLabel"
        :label="label"
        size="small"
        :data-testid="`${testid}-trigger`"
        @click="openMenu"
      >
        <Icon :name="icon" size="dense" />
      </IconButton>
      <Button
        v-else
        variant="text"
        :data-testid="`${testid}-trigger`"
        @click="openMenu"
      >
        <Icon :name="icon" size="dense" />
        <span>{{ label }}</span>
      </Button>
      <Sheet :open="sheetOpen" :title="label" :testid="`${testid}-sheet`" @close="sheetOpen = false">
        <div ref="panel" :data-testid="`${testid}-panel`">
          <ul class="menu__list" role="none" @keydown="onPanelKeydown">
            <template v-for="item in items" :key="item.id">
              <li v-if="item.separatorBefore" class="menu__separator" role="separator" />
              <li role="none">
                <button
                  class="menu__item"
                  :class="{ 'menu__item--danger': item.danger }"
                  type="button"
                  role="menuitem"
                  :disabled="item.disabled"
                  @click="select(item)"
                >
                  <Icon v-if="item.icon" :name="item.icon" size="dense" />
                  <span>{{ item.label }}</span>
                </button>
              </li>
            </template>
          </ul>
          <slot :close="closeMenu" />
        </div>
      </Sheet>
    </template>
  </span>
</template>

<style scoped>
.menu {
  display: inline-flex;
}

.menu__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 180px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.menu__item {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  width: 100%;
  min-height: var(--gv-size-control-lg);
  padding: 0 var(--gv-space-3);
  border: 0;
  border-radius: var(--gv-radius-sm);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
  text-align: start;
  cursor: pointer;
}

.menu__item:hover:not(:disabled) {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.menu__item:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.menu__item--danger {
  color: var(--gv-color-error);
}

.menu__item:disabled {
  color: var(--gv-color-on-surface);
  opacity: var(--gv-state-disabled);
  cursor: not-allowed;
}

.menu__separator {
  height: 1px;
  margin: var(--gv-space-1) 0;
  background: var(--gv-color-outline-variant);
}
</style>
