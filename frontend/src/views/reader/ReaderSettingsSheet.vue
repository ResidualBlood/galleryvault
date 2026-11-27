<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from "vue";
import Button from "@/components/ui/Button.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import type { IconName } from "@/components/icons/registry";
import {
  READER_FITS,
  READER_MODES,
  type ReaderFit,
  type ReaderMode,
} from "@/reader/pure";

const props = defineProps<{
  open: boolean;
  mode: ReaderMode;
  fit: ReaderFit;
  interval: number;
  slideshowOn: boolean;
  title: string;
  modeLabel: string;
  fitLabel: string;
  slideshowLabel: string;
  intervalLabel: string;
  intervalPlaceholder: string;
  intervalUnit: string;
  closeLabel: string;
  shortcuts: string;
  modeNames: Record<ReaderMode, string>;
  fitNames: Record<ReaderFit, string>;
}>();

const emit = defineEmits<{
  close: [];
  mode: [mode: ReaderMode];
  fit: [fit: ReaderFit];
  interval: [seconds: number];
  slideshow: [];
}>();

/** Two reading orders are visually identical to their single-page twin, so the
 *  registry reuses the same glyph and the label carries the distinction. */
const MODE_ICONS: Record<ReaderMode, IconName> = {
  ltr: "forward",
  rtl: "back",
  double: "view-grid",
  "double-rtl": "view-grid",
  webtoon: "view-list",
};

const modeOptions = computed(() =>
  READER_MODES.map((value) => ({
    value,
    label: props.modeNames[value],
    icon: MODE_ICONS[value],
  })),
);

const fitOptions = computed(() =>
  READER_FITS.map((value) => ({ value, label: props.fitNames[value] })),
);

const intervalDraft = ref(String(props.interval));

watch(
  () => props.interval,
  (value) => {
    intervalDraft.value = String(value);
  },
);

function onInterval(value: string): void {
  const parsed = Number.parseInt(value, 10);
  if (Number.isFinite(parsed)) emit("interval", parsed);
  else intervalDraft.value = String(props.interval);
}

function onMode(value: string): void {
  emit("mode", value as ReaderMode);
}

function onFit(value: string): void {
  emit("fit", value as ReaderFit);
}

const root = ref<HTMLDialogElement | null>(null);
const sheet = ref<HTMLElement | null>(null);
const titleId = useId();
let pressedOutside = false;

watch(
  () => props.open,
  async (open) => {
    if (open) {
      await nextTick();
      const dialog = root.value;
      if (dialog && !dialog.open) {
        dialog.showModal();
        dialog.dataset.gvModal = "";
      }
    } else {
      const dialog = root.value;
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
  const dialog = root.value;
  if (!dialog || event.target !== dialog) return false;
  const rect = sheet.value?.getBoundingClientRect();
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

onBeforeUnmount(() => {
  const dialog = root.value;
  if (dialog?.open) {
    delete dialog.dataset.gvModal;
    dialog.close();
  }
});
</script>

<template>
  <dialog
    v-if="open"
    ref="root"
    class="reader-settings"
    data-testid="reader-settings-panel"
    :aria-labelledby="titleId"
    @cancel="onCancel"
    @pointerdown="onPointerDown"
    @pointerup="onPointerUp"
  >
    <section ref="sheet" class="reader-settings__sheet">
      <header class="reader-settings__header">
        <h2 :id="titleId" class="reader-settings__title">{{ title }}</h2>
        <IconButton
          name="close"
          size="lg"
          :label="closeLabel"
          data-testid="reader-settings-close"
          @click="emit('close')"
        />
      </header>

      <div class="reader-settings__group">
        <p class="reader-settings__label">{{ modeLabel }}</p>
        <SegmentedControl
          class="reader-settings__segmented"
          testid="reader-mode-control"
          :model-value="mode"
          :options="modeOptions"
          :label="modeLabel"
          @change="onMode"
        />
      </div>

      <div class="reader-settings__group">
        <p class="reader-settings__label">{{ fitLabel }}</p>
        <SegmentedControl
          class="reader-settings__segmented"
          testid="reader-fit-control"
          :model-value="fit"
          :options="fitOptions"
          :label="fitLabel"
          @change="onFit"
        />
      </div>

      <div class="reader-settings__group">
        <p class="reader-settings__label">{{ slideshowLabel }}</p>
        <div class="reader-settings__row" data-gv-toolbar>
          <div class="reader-settings__interval">
            <Input
              v-model="intervalDraft"
              type="number"
              size="lg"
              :unit="intervalUnit"
              :placeholder="intervalPlaceholder"
              :aria-label="intervalLabel"
              data-testid="reader-settings-interval"
              @change="onInterval"
            />
          </div>
          <Button
            :variant="slideshowOn ? 'tonal' : 'outlined'"
            size="lg"
            :icon="slideshowOn ? 'pause' : 'play'"
            :aria-pressed="slideshowOn"
            data-testid="reader-settings-slideshow"
            @click="emit('slideshow')"
          >
            {{ slideshowLabel }}
          </Button>
        </div>
      </div>

      <p class="reader-settings__shortcuts">{{ shortcuts }}</p>
    </section>
  </dialog>
</template>

<style scoped>
.reader-settings {
  position: fixed;
  inset: 0;
  width: 100%;
  max-width: none;
  height: 100%;
  max-height: none;
  margin: 0;
  padding: var(--gv-space-3);
  border: 0;
  background: transparent;
  color: var(--gv-color-on-surface);
  overflow: hidden;
  overscroll-behavior: contain;
}

.reader-settings[open] {
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.reader-settings:modal {
  overscroll-behavior: contain;
}

.reader-settings::backdrop {
  background: color-mix(in srgb, var(--gv-color-scrim) 56%, transparent);
  overflow: hidden;
  overscroll-behavior: contain;
}

.reader-settings__sheet {
  width: min(560px, 100%);
  max-height: 80%;
  overflow-y: auto;
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-5);
  color: var(--gv-color-on-surface);
}

.reader-settings__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
  margin-bottom: var(--gv-space-3);
}

.reader-settings__title {
  margin: 0;
  font: var(--gv-type-title-medium);
}

.reader-settings__group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  margin-bottom: var(--gv-space-3);
}

.reader-settings__label {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.reader-settings__segmented {
  display: grid;
  width: 100%;
}

.reader-settings__segmented :deep(.segmented__item) {
  padding: 0 var(--gv-space-2);
}

.reader-settings__row {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
}

.reader-settings__interval {
  flex: none;
  width: 104px;
}

.reader-settings__shortcuts {
  margin: var(--gv-space-3) 0 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

@media (max-width: 599.98px) {
  /* Five segments have to share 334px: the icons step aside and the row wraps
     into a 3-column grid so no label has to be truncated. */
  .reader-settings__segmented {
    grid-auto-flow: row;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .reader-settings__segmented :deep(.gv-icon) {
    display: none;
  }

  .reader-settings__segmented :deep(.segmented__item) {
    padding: 0 var(--gv-space-1);
  }
}
</style>
