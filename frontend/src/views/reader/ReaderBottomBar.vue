<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  page: number;
  total: number;
  pageLabel: string;
  firstLabel: string;
  lastLabel: string;
  settingsLabel: string;
  slideshowLabel: string;
  slideshowOn: boolean;
  nextLabel: string;
  atEnd: boolean;
}>();

const emit = defineEmits<{
  first: [];
  last: [];
  seek: [page: number];
  settings: [];
  slideshow: [];
  next: [];
  interaction: [];
}>();

const progress = computed(() => {
  if (props.total <= 1) return 0;
  return (props.page / (props.total - 1)) * 100;
});

function onSeek(event: Event): void {
  const value = Number.parseInt((event.target as HTMLInputElement).value, 10);
  if (Number.isFinite(value)) emit("seek", value - 1);
}
</script>

<template>
  <footer class="reader-bottombar" data-testid="reader-bottombar">
    <button type="button" class="reader-bottombar__button" data-testid="reader-first" :title="firstLabel" @click="emit('first')">
      <span aria-hidden="true">|◀</span>
      <span class="sr-only">{{ firstLabel }}</span>
    </button>
    <div class="reader-bottombar__slider">
      <input
        class="reader-bottombar__range"
        data-testid="reader-slider"
        type="range"
        min="1"
        :max="Math.max(1, total)"
        :value="page + 1"
        :aria-label="pageLabel"
        :style="{ '--reader-progress': `${progress}%` }"
        @input="onSeek"
        @pointerdown="emit('interaction')"
      />
      <span class="reader-bottombar__label" data-testid="reader-slider-label">{{ pageLabel }}</span>
    </div>
    <button type="button" class="reader-bottombar__button" data-testid="reader-last" :title="lastLabel" @click="emit('last')">
      <span aria-hidden="true">▶|</span>
      <span class="sr-only">{{ lastLabel }}</span>
    </button>
    <button
      v-if="atEnd"
      type="button"
      class="reader-bottombar__button reader-bottombar__button--next"
      data-testid="reader-next-gallery"
      :title="nextLabel"
      @click="emit('next')"
    >
      <span aria-hidden="true">⇥</span>
      <span class="sr-only">{{ nextLabel }}</span>
    </button>
    <button
      type="button"
      class="reader-bottombar__button"
      :class="{ 'reader-bottombar__button--active': slideshowOn }"
      data-testid="reader-slideshow"
      :title="slideshowLabel"
      @click="emit('slideshow')"
    >
      <span aria-hidden="true">{{ slideshowOn ? '⏸' : '▶' }}</span>
      <span class="sr-only">{{ slideshowLabel }}</span>
    </button>
    <button type="button" class="reader-bottombar__button" data-testid="reader-settings" :title="settingsLabel" @click="emit('settings')">
      <span aria-hidden="true">⚙</span>
      <span class="sr-only">{{ settingsLabel }}</span>
    </button>
  </footer>
</template>

<style scoped>
.reader-bottombar {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-reader-bar);
  padding: 0 var(--gv-space-3);
  border-top: 1px solid var(--gv-color-outline-variant);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 92%, transparent);
  box-shadow: var(--gv-elev-3);
  color: var(--gv-color-on-surface);
  backdrop-filter: blur(8px);
  transition: transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.reader-bottombar__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 var(--gv-size-touch);
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  padding: 0;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.reader-bottombar__button:hover,
.reader-bottombar__button--active {
  background: color-mix(in srgb, var(--gv-color-primary) 24%, transparent);
  color: var(--gv-color-primary-text);
}

.reader-bottombar__button:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: 2px;
}

.reader-bottombar__button--next {
  color: var(--gv-color-warning);
}

.reader-bottombar__slider {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.reader-bottombar__range {
  flex: 1;
  min-width: 40px;
  height: var(--gv-size-touch);
  margin: 0;
  background: transparent;
  accent-color: var(--gv-color-primary);
  cursor: pointer;
}

.reader-bottombar__range::-webkit-slider-runnable-track {
  height: 6px;
  border-radius: var(--gv-radius-full);
  background: linear-gradient(
    to right,
    var(--gv-color-primary) var(--reader-progress, 0%),
    var(--gv-color-surface-variant) var(--reader-progress, 0%)
  );
}

.reader-bottombar__range::-moz-range-track {
  height: 6px;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
}

.reader-bottombar__range::-moz-range-progress {
  height: 6px;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.reader-bottombar__range::-webkit-slider-thumb {
  width: 16px;
  height: 16px;
  margin-top: -5px;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  box-shadow: var(--gv-elev-1);
  appearance: none;
}

.reader-bottombar__range::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.reader-bottombar__label {
  flex: 0 0 auto;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 599px) {
  .reader-bottombar__label {
    display: none;
  }
}
</style>
