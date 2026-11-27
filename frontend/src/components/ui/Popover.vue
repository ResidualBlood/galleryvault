<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  focusMenuItemFor,
  isMenuNavKey,
  menuItems,
} from "@/composables/useMenuKeyboard";

withDefaults(defineProps<{ align?: "start" | "end" }>(), { align: "start" });

const FOCUSABLE_SELECTOR =
  'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

const open = ref(false);
const root = ref<HTMLElement | null>(null);
/** Wrapper around the trigger slot; the interactive element lives inside. */
const trigger = ref<HTMLElement | null>(null);
const panel = ref<HTMLElement | null>(null);
/**
 * `menu` while the panel really holds menuitems, otherwise no role: the slot
 * content decides (AppShell popovers are button groups, Menu.vue items are
 * menuitems). Kept as `menu` until the first open to preserve Menu.vue.
 */
const panelRole = ref<string | undefined>("menu");

function triggerControl(): HTMLElement | null {
  return (
    trigger.value?.querySelector<HTMLElement>(
      'button, [role="button"], a[href], input, select, textarea',
    ) ?? null
  );
}

/** aria-expanded / aria-haspopup belong on the element inside the slot. */
function syncTrigger(): void {
  const el = triggerControl();
  if (!el) return;
  el.setAttribute("aria-expanded", String(open.value));
  if (panelRole.value === "menu") el.setAttribute("aria-haspopup", "menu");
  else el.removeAttribute("aria-haspopup");
}

/** A slot that renders menuitems keeps role=menu; anything else is a plain group. */
function syncPanelRole(): void {
  if (!panel.value) return;
  panelRole.value = panel.value.querySelector('[role="menuitem"]') ? "menu" : undefined;
}

function focusFirst(): void {
  const first =
    menuItems(panel.value)[0] ??
    panel.value?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
  first?.focus();
}

async function syncOpenState(): Promise<void> {
  await nextTick();
  syncPanelRole();
  syncTrigger();
  if (open.value) focusFirst();
}

watch(open, () => void syncOpenState());

function toggle(): void {
  open.value = !open.value;
}

function close(): void {
  open.value = false;
}

function closeAndRestore(): void {
  const el = triggerControl();
  open.value = false;
  void nextTick(() => el?.focus());
}

function onDocumentPointer(event: Event): void {
  if (!open.value || !root.value) return;
  if (!root.value.contains(event.target as Node)) close();
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !open.value || event.defaultPrevented) return;
  closeAndRestore();
}

function onPanelKeydown(event: KeyboardEvent): void {
  if (event.defaultPrevented) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeAndRestore();
    return;
  }
  if (event.key === "Tab") {
    close();
    return;
  }
  if (!isMenuNavKey(event.key)) return;
  if (focusMenuItemFor(panel.value, event.key)) event.preventDefault();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer);
  document.addEventListener("keydown", onDocumentKeydown);
  void nextTick(syncTrigger);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer);
  document.removeEventListener("keydown", onDocumentKeydown);
});

defineExpose({ open, close, toggle });
</script>

<template>
  <span ref="root" class="popover">
    <span ref="trigger" class="popover__trigger" @click="toggle">
      <slot name="trigger" :open="open" />
    </span>
    <Transition name="popover">
      <span
        v-if="open"
        ref="panel"
        class="popover__panel"
        :class="`popover__panel--${align}`"
        :role="panelRole"
        @keydown="onPanelKeydown"
      >
        <slot :close="close" />
      </span>
    </Transition>
  </span>
</template>

<style scoped>
.popover {
  position: relative;
  display: inline-flex;
}

.popover__trigger {
  display: inline-flex;
}

.popover__panel {
  position: absolute;
  top: calc(100% + var(--gv-space-1));
  z-index: 30;
  min-width: 180px;
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-3);
}

.popover__panel--start {
  left: 0;
}

.popover__panel--end {
  right: 0;
}

.popover-enter-active,
.popover-leave-active {
  transition: opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.popover-enter-from,
.popover-leave-to {
  opacity: 0;
}
</style>
