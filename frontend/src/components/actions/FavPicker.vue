<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Sheet from "@/components/ui/Sheet.vue";
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
const { t } = useI18n();

const compact = ref(false);
const host = ref<string | HTMLElement>("body");
const desktop = ref<HTMLDialogElement | null>(null);
let pressedOutside = false;
let media: MediaQueryList | null = null;

function sync(event?: MediaQueryListEvent): void {
  compact.value = event ? event.matches : Boolean(media?.matches);
}

function modalHost(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  const open = document.querySelectorAll<HTMLElement>("[data-gv-modal]");
  return open.length ? open[open.length - 1] : null;
}

watch(
  () => [props.open, compact.value] as const,
  async ([open, isCompact]) => {
    const dialog = desktop.value;
    if (open && !isCompact) {
      host.value = modalHost() ?? "body";
      await nextTick();
      const el = desktop.value;
      if (el && !el.open) {
        el.showModal();
        el.dataset.gvModal = "";
      }
    } else if (dialog?.open) {
      delete dialog.dataset.gvModal;
      dialog.close();
    }
  },
  { immediate: true },
);

function onCancel(event: Event): void {
  event.preventDefault();
  emit("close");
}

function outside(event: MouseEvent): boolean {
  const rect = desktop.value?.getBoundingClientRect();
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
  <Sheet
    v-if="compact"
    :open="open"
    :title="t('actions.favoriteSelect')"
    testid="fav-sheet"
    @close="emit('close')"
  >
    <FavPickerPanel
      v-if="open"
      :gid="gid"
      :token="token"
      :favorited="favorited"
      :favcat="favcat"
      :note="note"
      :disabled="disabled"
      :heading="false"
      @done="emit('close')"
    />
  </Sheet>

  <Teleport v-else :to="host">
    <dialog
      v-if="open"
      ref="desktop"
      class="fav-picker"
      data-testid="fav-picker"
      :aria-label="t('actions.favoriteSelect')"
      @cancel="onCancel"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
    >
      <FavPickerPanel
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

.fav-picker:modal {
  overscroll-behavior: contain;
}

.fav-picker::backdrop {
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
  overflow: hidden;
  overscroll-behavior: contain;
}
</style>
