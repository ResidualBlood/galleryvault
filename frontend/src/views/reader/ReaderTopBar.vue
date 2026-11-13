<!-- gv-polish:pending -->
<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  title: string;
  pageLabel: string;
  jumpValue: number;
  total: number;
  jumpLabel: string;
  jumpHint: string;
  closeLabel: string;
  fullscreenLabel: string;
}>();

const emit = defineEmits<{
  close: [];
  jump: [page: number];
  fullscreen: [];
}>();

const jumpInput = ref<HTMLInputElement | null>(null);

function submitJump(): void {
  const value = Number.parseInt(jumpInput.value?.value ?? "", 10);
  if (Number.isFinite(value)) emit("jump", value - 1);
}

function focusJump(): void {
  jumpInput.value?.focus();
  jumpInput.value?.select();
}

defineExpose({ focusJump });
</script>

<template>
  <header class="reader-topbar" data-testid="reader-topbar">
    <button type="button" class="reader-icon" data-testid="reader-close" :title="closeLabel" @click="emit('close')">
      <span aria-hidden="true">←</span>
      <span class="sr-only">{{ closeLabel }}</span>
    </button>
    <p class="reader-topbar__title" :title="title">{{ title }}</p>
    <div class="reader-topbar__jump">
      <label class="reader-topbar__jump-label" :title="jumpHint">
        <span class="sr-only">{{ jumpLabel }}</span>
        <input
          ref="jumpInput"
          class="reader-topbar__input"
          data-testid="reader-jump"
          type="number"
          min="1"
          :max="total"
          :value="jumpValue"
          inputmode="numeric"
          :aria-label="jumpLabel"
          @change="submitJump"
          @keydown.enter.prevent="submitJump"
        />
      </label>
      <span class="reader-topbar__page" data-testid="reader-page-label">{{ pageLabel }}</span>
    </div>
    <button type="button" class="reader-icon" data-testid="reader-fullscreen" :title="fullscreenLabel" @click="emit('fullscreen')">
      <span aria-hidden="true">⛶</span>
      <span class="sr-only">{{ fullscreenLabel }}</span>
    </button>
  </header>
</template>

<style scoped>
.reader-topbar {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  height: var(--gv-size-reader-bar);
  padding: 0 var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: color-mix(in srgb, var(--gv-color-surface-container-high) 92%, transparent);
  box-shadow: var(--gv-elev-3);
  color: var(--gv-color-on-surface);
  backdrop-filter: blur(8px);
  transition: transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.reader-topbar__title {
  flex: 1;
  overflow: hidden;
  margin: 0;
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reader-topbar__jump {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.reader-topbar__jump-label {
  display: inline-flex;
}

.reader-topbar__input {
  width: 4.5em;
  min-height: 36px;
  padding: 0 var(--gv-space-1);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  text-align: center;
}

.reader-topbar__page {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  white-space: nowrap;
}

.reader-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  padding: 0;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
  cursor: pointer;
}

.reader-icon:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 12%, transparent);
}

.reader-icon:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: 2px;
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
  .reader-topbar__title {
    display: none;
  }
}
</style>
