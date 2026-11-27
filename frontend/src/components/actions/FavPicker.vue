<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";
import { useModalHost } from "@/composables/useModalHost";
import FavPickerPanel from "./FavPickerPanel.vue";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

const props = withDefaults(
  defineProps<{
    open: boolean;
    gid: number;
    token: string;
    favorited: boolean;
    favcat: number | null;
    note?: string | null;
    disabled?: boolean;
  }>(),
  { note: "", disabled: false },
);

const emit = defineEmits<{ close: [] }>();

const compact = ref(false);
// The panel owns the visible heading; the dialog takes its accessible name
// from it at both breakpoints (the sheet used to bring its own <h2>).
const titleId = useId();
const { host, refresh: refreshHost } = useModalHost();
const desktop = ref<HTMLDialogElement | null>(null);
let pressedOutside = false;
let media: MediaQueryList | null = null;

function sync(event?: MediaQueryListEvent): void {
  compact.value = event ? event.matches : Boolean(media?.matches);
}

// One native dialog for both breakpoints: only its layout changes. Swapping
// between a Sheet and the desktop dialog while open used to host the new
// dialog inside the old, soon-to-unmount modal, losing it together with focus.
watch(
  () => props.open,
  async (open) => {
    if (open) {
      refreshHost();
      await nextTick();
      const el = desktop.value;
      if (el && !el.open) {
        el.showModal();
        el.dataset.gvModal = "";
      }
    } else {
      const dialog = desktop.value;
      if (dialog?.open) {
        delete dialog.dataset.gvModal;
        dialog.close();
      }
    }
  },
  { immediate: true },
);

function onCancel(event: Event): void {
  event.preventDefault();
  emit("close");
}

function outside(event: MouseEvent): boolean {
  const dialog = desktop.value;
  // Only the dialog itself (backdrop / padding area) counts as outside; a
  // nested overlay teleported into the dialog stays inside.
  if (!dialog || event.target !== dialog) return false;
  const rect = dialog.getBoundingClientRect();
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
  if (pressedOutside && outside(event)) emit("close");
  pressedOutside = false;
}

onMounted(() => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  media = window.matchMedia("(max-width: 599px)");
  sync();
  media.addEventListener("change", sync);
});

onBeforeUnmount(() => {
  media?.removeEventListener("change", sync);
  if (desktop.value?.open) {
    delete desktop.value.dataset.gvModal;
    desktop.value.close();
  }
});
</script>

<template>
  <Teleport :to="host">
    <dialog
      v-if="open"
      ref="desktop"
      class="fav-picker"
      :class="{ 'fav-picker--compact': compact }"
      :data-testid="compact ? 'fav-sheet' : 'fav-picker'"
      :aria-labelledby="titleId"
      @cancel="onCancel"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
    >
      <div v-if="compact" class="fav-picker__handle" aria-hidden="true" />
      <FavPickerPanel
        :heading-id="titleId"
        :gid="gid"
        :token="token"
        :favorited="favorited"
        :favcat="favcat"
        :note="note"
        :disabled="disabled"
        @done="emit('close')"
      />
    </dialog>
  </Teleport>
</template>

<style scoped>
.fav-picker {
  position: fixed;
  inset: 0;
  width: min(360px, calc(100vw - var(--gv-space-6)));
  max-height: calc(100dvh - var(--gv-space-6));
  margin: auto;
  overflow: auto;
  padding: var(--gv-space-3);
  border: 0;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-3);
  overscroll-behavior: contain;
}

.fav-picker--compact {
  inset: auto 0 0 0;
  width: 100%;
  max-width: 640px;
  max-height: 90dvh;
  margin: 0 auto;
  border-radius: var(--gv-radius-xl) var(--gv-radius-xl) 0 0;
}

/* Decorative only, matching the sheet handle other bottom sheets show. */
.fav-picker__handle {
  width: 32px;
  height: 4px;
  margin: 0 auto var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-outline);
}

.fav-picker:modal {
  overscroll-behavior: contain;
}

.fav-picker::backdrop {
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
  overflow: hidden;
  overscroll-behavior: contain;
}
</style>
