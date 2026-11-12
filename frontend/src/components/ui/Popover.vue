<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

withDefaults(defineProps<{ align?: "start" | "end" }>(), { align: "start" });

const open = ref(false);
const root = ref<HTMLElement | null>(null);

function toggle(): void {
  open.value = !open.value;
}

function close(): void {
  open.value = false;
}

function onDocumentPointer(event: Event): void {
  if (!open.value || !root.value) return;
  if (!root.value.contains(event.target as Node)) close();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") close();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer);
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer);
  document.removeEventListener("keydown", onKeydown);
});

defineExpose({ open, close, toggle });
</script>

<template>
  <span ref="root" class="popover">
    <span class="popover__trigger" @click="toggle">
      <slot name="trigger" :open="open" />
    </span>
    <Transition name="popover">
      <span
        v-if="open"
        class="popover__panel"
        :class="`popover__panel--${align}`"
        role="menu"
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
