<script setup lang="ts">
import { computed } from "vue";
import IconButton from "@/components/ui/IconButton.vue";
import Slider from "@/components/ui/Slider.vue";

const props = defineProps<{
  page: number;
  total: number;
  pageLabel: string;
  firstLabel: string;
  prevLabel: string;
  nextPageLabel: string;
  lastLabel: string;
  settingsLabel: string;
  slideshowLabel: string;
  slideshowOn: boolean;
  nextLabel: string;
  atEnd: boolean;
}>();

const emit = defineEmits<{
  first: [];
  prev: [];
  nextPage: [];
  last: [];
  seek: [page: number];
  settings: [];
  slideshow: [];
  next: [];
  interaction: [];
}>();

/** The slider speaks 1-based page numbers; the shell contract stays 0-based. */
const sliderValue = computed(() => props.page + 1);
const sliderMax = computed(() => Math.max(1, props.total));

function onSeek(value: number): void {
  if (Number.isFinite(value)) emit("seek", value - 1);
}
</script>

<template>
  <footer class="reader-bottombar" data-testid="reader-bottombar" data-gv-toolbar>
    <IconButton
      name="first-page"
      size="lg"
      :label="firstLabel"
      data-testid="reader-first"
      @click="emit('first')"
    />
    <IconButton
      name="chevron-left"
      size="lg"
      :label="prevLabel"
      data-testid="reader-prev"
      @click="emit('prev')"
    />
    <Slider
      class="reader-bottombar__slider"
      data-testid="reader-slider"
      :model-value="sliderValue"
      :min="1"
      :max="sliderMax"
      :aria-label="pageLabel"
      @update:model-value="onSeek"
      @pointerdown="emit('interaction')"
    />
    <IconButton
      name="chevron-right"
      size="lg"
      :label="nextPageLabel"
      data-testid="reader-next"
      @click="emit('nextPage')"
    />
    <IconButton
      name="last-page"
      size="lg"
      :label="lastLabel"
      data-testid="reader-last"
      @click="emit('last')"
    />
    <IconButton
      v-if="atEnd"
      name="next-chapter"
      size="lg"
      :label="nextLabel"
      class="reader-bottombar__next"
      data-testid="reader-next-gallery"
      @click="emit('next')"
    />
    <IconButton
      :name="slideshowOn ? 'pause' : 'play'"
      size="lg"
      :label="slideshowLabel"
      :selected="slideshowOn"
      :class="{ 'reader-bottombar__slideshow--active': slideshowOn }"
      class="reader-bottombar__slideshow"
      data-testid="reader-slideshow"
      @click="emit('slideshow')"
    />
    <IconButton
      name="settings"
      size="lg"
      :label="settingsLabel"
      data-testid="reader-settings"
      @click="emit('settings')"
    />
  </footer>
</template>

<style scoped>
.reader-bottombar {
  position: absolute;
  inset: auto 0 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  height: var(--gv-size-reader-bar);
  padding: 0 var(--gv-space-3);
  border-top: 1px solid var(--gv-color-outline-variant);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 92%, transparent);
  box-shadow: var(--gv-elev-3);
  color: var(--gv-color-on-surface);
  backdrop-filter: blur(8px);
  transition: transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

/* One ladder step for the whole row: the shared slider is 44px tall by
   default, so pin it to the lg step here (the thumb keeps its 20px size). */
.reader-bottombar__slider {
  flex: 1 1 auto;
  min-width: 40px;
}

.reader-bottombar :deep(.slider__input) {
  height: var(--gv-size-control-lg);
}

.reader-bottombar__next {
  color: var(--gv-color-warning);
}

.reader-bottombar__slideshow--active {
  color: var(--gv-color-primary-text);
}

@media (max-width: 599.98px) {
  /* The slideshow lives in the settings sheet on a phone so the row keeps its
     breathing room (RD-07 / OR-09). */
  .reader-bottombar__slideshow {
    display: none;
  }
}
</style>
