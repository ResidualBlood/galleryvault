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
    testid: "dialog",
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
    <Transition name="dialog" @after-leave="onAfterLeave">
      <dialog
        v-if="open"
        ref="root"
        class="dialog"
        :aria-labelledby="title ? titleId : undefined"
        :data-testid="testid"
        @cancel="onCancel"
        @pointerdown="onPointerDown"
        @pointerup="onPointerUp"
      >
        <div ref="panel" class="dialog__panel">
          <header v-if="title || $slots.header" class="dialog__header">
            <slot name="header">
              <h2 :id="titleId" class="dialog__title">{{ title }}</h2>
            </slot>
          </header>
          <div class="dialog__body">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="dialog__footer">
            <slot name="footer" />
          </footer>
        </div>
      </dialog>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog {
  position: fixed;
  inset: 0;
  width: 100%;
  max-width: none;
  height: 100%;
  max-height: none;
  margin: 0;
  padding: var(--gv-space-4);
  border: 0;
  background: transparent;
  color: var(--gv-color-on-surface);
  overflow: hidden;
  transition-property: display, overlay;
  transition-duration: var(--gv-motion-duration-medium);
  transition-timing-function: var(--gv-motion-ease-standard);
  transition-behavior: allow-discrete;
}

.dialog[open] {
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog:modal {
  overscroll-behavior: contain;
}

.dialog::backdrop {
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
  overflow: hidden;
  overscroll-behavior: contain;
}

.dialog__panel {
  position: relative;
  width: min(560px, calc(100vw - var(--gv-space-6)));
  max-height: min(90vh, 720px);
  overflow: auto;
  padding: var(--gv-space-5);
  border-radius: var(--gv-radius-xl);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-5);
  overscroll-behavior: contain;
}

.dialog__header {
  margin-bottom: var(--gv-space-3);
}

.dialog__title {
  margin: 0;
  font: var(--gv-type-headline-small);
}

.dialog__body {
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-5);
}

.dialog-enter-active,
.dialog-leave-active {
  transition-property: opacity, display, overlay;
  transition-duration: var(--gv-motion-duration-medium);
  transition-timing-function: var(--gv-motion-ease-standard);
  transition-behavior: allow-discrete;
}

.dialog-leave-active {
  pointer-events: none;
}

.dialog-enter-active .dialog__panel,
.dialog-leave-active .dialog__panel {
  transition: transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}

.dialog-enter-from .dialog__panel,
.dialog-leave-to .dialog__panel {
  transform: translateY(8px);
}

@media (prefers-reduced-motion: reduce) {
  .dialog-enter-active,
  .dialog-leave-active,
  .dialog-enter-active .dialog__panel,
  .dialog-leave-active .dialog__panel {
    transition-duration: 1ms;
  }
}
</style>
