<!-- gv-polish:pending -->
<script setup lang="ts">
import {
  READER_FITS,
  READER_MODES,
  type ReaderFit,
  type ReaderMode,
} from "@/reader/pure";

defineProps<{
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

function onInterval(event: Event): void {
  const value = Number.parseInt((event.target as HTMLInputElement).value, 10);
  if (Number.isFinite(value)) emit("interval", value);
}
</script>

<template>
  <div v-if="open" class="reader-settings" data-testid="reader-settings-panel" @click.self="emit('close')">
    <section class="reader-settings__sheet" role="dialog" aria-modal="true" :aria-label="title">
      <header class="reader-settings__header">
        <h2 class="reader-settings__title">{{ title }}</h2>
        <button type="button" class="reader-settings__close" :aria-label="closeLabel" @click="emit('close')">
          <span aria-hidden="true">✕</span>
        </button>
      </header>

      <p class="reader-settings__label">{{ modeLabel }}</p>
      <div class="reader-settings__options" role="group" :aria-label="modeLabel">
        <button
          v-for="value in READER_MODES"
          :key="value"
          type="button"
          class="reader-settings__option"
          :class="{ 'reader-settings__option--active': mode === value }"
          :aria-pressed="mode === value"
          :data-mode="value"
          @click="emit('mode', value)"
        >
          {{ modeNames[value] }}
        </button>
      </div>

      <p class="reader-settings__label">{{ fitLabel }}</p>
      <div class="reader-settings__options" role="group" :aria-label="fitLabel">
        <button
          v-for="value in READER_FITS"
          :key="value"
          type="button"
          class="reader-settings__option"
          :class="{ 'reader-settings__option--active': fit === value }"
          :aria-pressed="fit === value"
          :data-fit="value"
          @click="emit('fit', value)"
        >
          {{ fitNames[value] }}
        </button>
      </div>

      <p class="reader-settings__label">{{ slideshowLabel }}</p>
      <div class="reader-settings__row">
        <label class="reader-settings__interval">
          <span>{{ intervalLabel }}</span>
          <input
            class="reader-settings__input"
            type="number"
            min="1"
            max="600"
            step="1"
            :value="interval"
            @change="onInterval"
          />
        </label>
        <button
          type="button"
          class="reader-settings__option reader-settings__option--slideshow"
          :class="{ 'reader-settings__option--active': slideshowOn }"
          :aria-pressed="slideshowOn"
          data-testid="reader-settings-slideshow"
          @click="emit('slideshow')"
        >
          {{ slideshowOn ? '⏸' : '▶' }} {{ slideshowLabel }}
        </button>
      </div>

      <p class="reader-settings__shortcuts">{{ shortcuts }}</p>
    </section>
  </div>
</template>

<style scoped>
.reader-settings {
  position: absolute;
  inset: 0;
  z-index: 6;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: var(--gv-space-3);
  background: color-mix(in srgb, var(--gv-color-scrim) 56%, transparent);
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

.reader-settings__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  padding: 0;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-title-small);
  cursor: pointer;
}

.reader-settings__close:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.reader-settings__label {
  margin: var(--gv-space-3) 0 var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.reader-settings__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.reader-settings__option {
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.reader-settings__option:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.reader-settings__option--active {
  border-color: var(--gv-color-primary);
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.reader-settings__option:focus-visible,
.reader-settings__close:focus-visible,
.reader-settings__input:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: 2px;
}

.reader-settings__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.reader-settings__interval {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.reader-settings__input {
  width: 5em;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  text-align: center;
}

.reader-settings__option--slideshow {
  min-width: 8em;
}

.reader-settings__shortcuts {
  margin: var(--gv-space-4) 0 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
