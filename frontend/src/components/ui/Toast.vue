<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useUiStore } from "@/stores/ui";

const ui = useUiStore();
const { t } = useI18n();

const hostEl = ref<HTMLElement | null>(null);

// Popover is Baseline newly available (2025-01); keep the fixed-position host
// as the fallback when the API is missing. Feature detect on the prototype so
// the attribute is never set in unsupporting browsers.
const supportsPopover =
  typeof HTMLElement !== "undefined" &&
  Object.hasOwn(HTMLElement.prototype, "popover") &&
  typeof (HTMLElement.prototype as { showPopover?: unknown }).showPopover === "function";
const popoverMode = supportsPopover ? "manual" : undefined;
let topLayerShown = false;

type PopoverHost = HTMLElement & { showPopover?: () => void; hidePopover?: () => void };

/**
 * A popover sits above a modal dialog's top layer only if it was opened after
 * it, so re-show the host whenever the stack grows. Skipping the re-show while
 * focus is inside avoids blurring a paused toast.
 */
function syncTopLayer(): void {
  const host = hostEl.value as PopoverHost | null;
  if (!host || !supportsPopover) return;

  if (ui.toasts.length === 0) {
    if (topLayerShown) {
      try {
        host.hidePopover?.();
      } catch {
        /* already hidden */
      }
      topLayerShown = false;
    }
    return;
  }

  const active = typeof document !== "undefined" ? document.activeElement : null;
  const focusInside = !!active && host.contains(active);
  try {
    if (topLayerShown) {
      if (!focusInside) {
        host.hidePopover?.();
        host.showPopover?.();
      }
    } else {
      host.showPopover?.();
      topLayerShown = true;
    }
  } catch {
    topLayerShown = false;
  }
}

// flush: "pre" shows the (top layer) host before the new text is inserted, so
// the live region is visible when the announcement fires.
watch(
  () => ui.toasts.map((toast) => toast.id).join(","),
  () => syncTopLayer(),
  { flush: "pre" },
);

onMounted(syncTopLayer);

function onFocusOut(event: FocusEvent, id: number): void {
  const current = event.currentTarget as HTMLElement | null;
  const next = event.relatedTarget as Node | null;
  if (current && next && current.contains(next)) return;
  ui.resumeToast(id, "focus");
}

function closeToast(id: number): void {
  const revert = ui.returnFocusFor(id);
  const index = ui.toasts.findIndex((toast) => toast.id === id);
  const remaining = ui.toasts.filter((toast) => toast.id !== id);
  const next = remaining[Math.min(Math.max(index, 0), remaining.length - 1)];
  ui.dismiss(id);
  void nextTick(() => {
    const host = hostEl.value;
    const nextButton =
      next != null
        ? host?.querySelector<HTMLElement>(`[data-toast-id="${next.id}"] .toast__close`)
        : null;
    if (nextButton) {
      nextButton.focus();
    } else if (revert && revert.isConnected) {
      revert.focus();
    }
  });
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="hostEl"
      class="toast-host"
      role="region"
      :aria-label="t('common.toastRegion')"
      aria-live="polite"
      :popover="popoverMode"
    >
      <TransitionGroup name="toast" tag="div" class="toast-list">
        <div
          v-for="toast in ui.toasts"
          :key="toast.id"
          class="toast"
          :class="`toast--${toast.kind}`"
          :data-toast-id="toast.id"
          @pointerenter="ui.pauseToast(toast.id, 'pointer')"
          @pointerleave="ui.resumeToast(toast.id, 'pointer')"
          @focusin="ui.pauseToast(toast.id, 'focus')"
          @focusout="onFocusOut($event, toast.id)"
        >
          <span class="toast__text">{{ toast.text }}</span>
          <button class="toast__close" type="button" @click="closeToast(toast.id)">
            {{ t("common.close") }}
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed;
  inset: auto;
  right: var(--gv-space-4);
  bottom: var(--gv-space-4);
  z-index: 50;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  overflow: visible;
  pointer-events: none;
}

.toast-list {
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

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    transition: none;
  }

  .toast-enter-from,
  .toast-leave-to {
    transform: none;
  }
}
</style>
