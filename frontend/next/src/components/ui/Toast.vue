<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useUiStore } from "@/stores/ui";

const ui = useUiStore();
const { t } = useI18n();
</script>

<template>
  <Teleport to="body">
    <TransitionGroup name="toast" tag="div" class="toast-host" aria-live="polite">
      <div
        v-for="toast in ui.toasts"
        :key="toast.id"
        class="toast"
        :class="`toast--${toast.kind}`"
        role="status"
      >
        <span class="toast__text">{{ toast.text }}</span>
        <button class="toast__close" type="button" @click="ui.dismiss(toast.id)">
          {{ t("common.close") }}
        </button>
      </div>
    </TransitionGroup>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed;
  right: var(--gv-space-4);
  bottom: var(--gv-space-4);
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  min-height: 48px;
  max-width: min(420px, calc(100vw - var(--gv-space-6)));
  padding: var(--gv-space-2) var(--gv-space-3) var(--gv-space-2) var(--gv-space-4);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-inverse-surface);
  color: var(--gv-color-inverse-on-surface);
  box-shadow: var(--gv-elev-3);
  pointer-events: auto;
}

.toast--error {
  border-inline-start: var(--gv-state-focus-ring-width) solid var(--gv-color-error);
}

.toast--success {
  border-inline-start: var(--gv-state-focus-ring-width) solid var(--gv-color-success);
}

.toast__text {
  flex: 1;
  font: var(--gv-type-body-medium);
}

.toast__close {
  border: 0;
  background: transparent;
  color: var(--gv-color-inverse-primary);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard),
    transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 599px) {
  .toast-host {
    left: var(--gv-space-4);
    right: var(--gv-space-4);
    bottom: var(--gv-space-3);
  }
}
</style>
