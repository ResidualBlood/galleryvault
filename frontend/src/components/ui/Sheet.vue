<script setup lang="ts">
import { nextTick, ref, useId, watch } from "vue";
import { useModalHost } from "@/composables/useModalHost";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    dismissible?: boolean;
    testid?: string;
  }>(),
  {
    title: "",
    dismissible: true,
    testid: "sheet",
  },
);

const emit = defineEmits<{ close: [] }>();
const root = ref<HTMLDialogElement | null>(null);
const panel = ref<HTMLElement | null>(null);
const { host, refresh: refreshHost, reset: resetHost } = useModalHost();
const titleId = useId();
let pressedOutside = false;

watch(
  () => props.open,
  async (open) => {
    if (open) {
      refreshHost();
      await nextTick();
      const dialog = root.value;
      if (dialog && !dialog.open) {
        dialog.showModal();
        dialog.dataset.gvModal = "";
        dialog.removeAttribute("aria-hidden");
      }
    } else {
      const dialog = root.value;
      if (dialog?.open) {
        delete dialog.dataset.gvModal;
        dialog.close();
        // The element stays mounted for the leave transition; keep the fading
        // copy out of the accessibility tree so only the new dialog is exposed.
        dialog.setAttribute("aria-hidden", "true");
      }
    }
  },
  { immediate: true },
);

function requestClose(): void {
  if (props.dismissible) emit("close");
}

function onCancel(event: Event): void {
  event.preventDefault();
  requestClose();
}

function outside(event: MouseEvent): boolean {
  const rect = panel.value?.getBoundingClientRect();
  if (!rect) return false;
  return (
    event.clientX < rect.left ||
    event.clientX > rect.right ||
    event.clientY < rect.top ||
    event.clientY > rect.bottom
  );
}

function onPointerDown(event: MouseEvent): void {
  pressedOutside = outside(event);
}

function onPointerUp(event: MouseEvent): void {
  if (pressedOutside && outside(event)) requestClose();
  pressedOutside = false;
}

function onAfterLeave(): void {
  resetHost();
}
</script>

<template>
  <Teleport :to="host">
    <Transition name="sheet" @after-leave="onAfterLeave">
      <dialog
        v-if="open"
        ref="root"
        class="sheet"
        :aria-labelledby="title ? titleId : undefined"
        @cancel="onCancel"
        @pointerdown="onPointerDown"
        @pointerup="onPointerUp"
      >
        <section ref="panel" class="sheet__panel" :data-testid="testid">
          <div class="sheet__handle" aria-hidden="true" />
          <header v-if="title" class="sheet__header">
            <h2 :id="titleId" class="sheet__title">{{ title }}</h2>
          </header>
          <div class="sheet__body"><slot /></div>
          <footer v-if="$slots.footer" class="sheet__footer"><slot name="footer" /></footer>
        </section>
      </dialog>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet {
  position: fixed;
  inset: 0;
  width: 100%;
  max-width: none;
  height: 100%;
  max-height: none;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--gv-color-on-surface);
  overflow: hidden;
  transition-property: display, overlay;
  transition-duration: var(--gv-motion-duration-long);
  transition-timing-function: var(--gv-motion-ease-standard);
  transition-behavior: allow-discrete;
}

.sheet[open] {
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.sheet:modal {
  overscroll-behavior: contain;
}

.sheet::backdrop {
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
  overflow: hidden;
  overscroll-behavior: contain;
}

.sheet__panel {
  position: relative;
  width: min(640px, 100vw);
  max-height: 90vh;
  overflow: auto;
  padding: var(--gv-space-3) var(--gv-space-4) var(--gv-space-5);
  border-radius: var(--gv-radius-xl) var(--gv-radius-xl) 0 0;
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-4);
  overscroll-behavior: contain;
}

.sheet__handle {
  width: 32px;
  height: 4px;
  margin: 0 auto var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-outline);
}

.sheet__header {
  margin-bottom: var(--gv-space-2);
}

.sheet__title {
  margin: 0;
  font: var(--gv-type-title-medium);
}

.sheet__body {
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.sheet__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-4);
}

.sheet-enter-active,
.sheet-leave-active {
  transition-property: opacity, display, overlay;
  transition-duration: var(--gv-motion-duration-long);
  transition-timing-function: var(--gv-motion-ease-standard);
  transition-behavior: allow-discrete;
}

.sheet-leave-active {
  pointer-events: none;
}

.sheet-enter-active .sheet__panel,
.sheet-leave-active .sheet__panel {
  transition: transform var(--gv-motion-duration-long) var(--gv-motion-ease-standard);
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}

.sheet-enter-from .sheet__panel,
.sheet-leave-to .sheet__panel {
  transform: translateY(100%);
}

@media (min-width: 840px) {
  .sheet[open] {
    align-items: center;
    justify-content: flex-end;
  }

  .sheet__panel {
    height: 100%;
    max-height: none;
    width: min(420px, 100vw);
    border-radius: var(--gv-radius-xl) 0 0 var(--gv-radius-xl);
  }

  .sheet-enter-from .sheet__panel,
  .sheet-leave-to .sheet__panel {
    transform: translateX(100%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .sheet-enter-active,
  .sheet-leave-active,
  .sheet-enter-active .sheet__panel,
  .sheet-leave-active .sheet__panel {
    transition-duration: 1ms;
  }
}
</style>
