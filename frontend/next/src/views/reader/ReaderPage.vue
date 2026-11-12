<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderFit } from "@/reader/pure";

const props = defineProps<{
  page: number;
  src: string | null;
  fit: ReaderFit;
  alt: string;
  failed: boolean;
  placeholder: string;
  retryLabel: string;
}>();

const emit = defineEmits<{
  load: [info: { page: number; width: number; height: number }];
  error: [page: number];
  retry: [page: number];
}>();

const loaded = ref(false);

watch(
  () => [props.src, props.page],
  () => {
    loaded.value = false;
  },
);

function onLoad(event: Event): void {
  const image = event.target as HTMLImageElement;
  loaded.value = true;
  emit("load", {
    page: props.page,
    width: image.naturalWidth,
    height: image.naturalHeight,
  });
}
</script>

<template>
  <div class="reader-page" :data-page="page" data-testid="reader-page">
    <div v-if="failed" class="reader-page__missing" data-testid="reader-page-missing">
      <span class="reader-page__missing-text">{{ placeholder }}</span>
      <button type="button" class="reader-page__retry" data-testid="reader-retry" @click="emit('retry', page)">
        {{ retryLabel }}
      </button>
    </div>
    <div v-else-if="src" class="reader-page__frame" :class="{ 'reader-page__frame--loaded': loaded }">
      <img
        :src="src"
        :alt="alt"
        :class="`reader-page__image reader-page__image--${fit}`"
        decoding="async"
        draggable="false"
        referrerpolicy="no-referrer"
        @load="onLoad"
        @error="emit('error', page)"
      />
    </div>
    <div v-else class="reader-page__skeleton" aria-hidden="true" />
  </div>
</template>

<style scoped>
.reader-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
}

.reader-page__frame {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  opacity: 0;
  transition: opacity var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.reader-page__frame--loaded {
  opacity: 1;
}

.reader-page__image {
  display: block;
  max-width: 100%;
  max-height: 100%;
  user-select: none;
}

.reader-page__image--height {
  width: auto;
  height: 100%;
  object-fit: contain;
}

.reader-page__image--width {
  width: 100%;
  height: auto;
  object-fit: contain;
}

.reader-page__image--original {
  width: auto;
  height: auto;
  max-width: none;
  max-height: none;
  object-fit: none;
}

.reader-page__skeleton {
  width: min(70%, var(--gv-size-content-max));
  height: 70%;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
  opacity: var(--gv-state-disabled-container);
}

.reader-page__missing {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--gv-space-3);
  max-width: min(360px, 86%);
  padding: var(--gv-space-5);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.reader-page__missing-text {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-align: center;
}

.reader-page__retry {
  pointer-events: auto;
  min-width: var(--gv-size-touch);
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.reader-page__retry:hover {
  background: color-mix(in srgb, var(--gv-color-primary) 12%, transparent);
}

.reader-page__retry:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: 2px;
}
</style>
