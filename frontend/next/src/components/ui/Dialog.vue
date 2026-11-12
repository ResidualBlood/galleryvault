<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    dismissible?: boolean;
    testid?: string;
  }>(),
  {
    title: "",
    dismissible: true,
    testid: "dialog",
  },
);

const emit = defineEmits<{ close: [] }>();
const panel = ref<HTMLElement | null>(null);
const titleId = `gv-dialog-title-${Math.random().toString(36).slice(2, 9)}`;
let previousFocus: HTMLElement | null = null;

watch(
  () => props.open,
  async (open) => {
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      await nextTick();
      panel.value?.focus();
    } else {
      previousFocus?.focus();
      previousFocus = null;
    }
  },
);

function requestClose(): void {
  if (props.dismissible) emit("close");
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && props.open) requestClose();
}

onMounted(() => document.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => document.removeEventListener("keydown", onKeydown));
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="open" class="dialog">
        <div class="dialog__scrim" @click="requestClose" />
        <section
          ref="panel"
          class="dialog__panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="title ? titleId : undefined"
          :data-testid="testid"
          tabindex="-1"
        >
          <header v-if="title || $slots.header" class="dialog__header">
            <slot name="header">
              <h2 :id="titleId" class="dialog__title">{{ title }}</h2>
            </slot>
          </header>
          <div class="dialog__body">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="dialog__footer">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--gv-space-4);
}

.dialog__scrim {
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
}

.dialog__panel {
  position: relative;
  width: min(560px, calc(100vw - var(--gv-space-6)));
  max-height: min(90vh, 720px);
  overflow: auto;
  padding: var(--gv-space-5);
  border-radius: var(--gv-radius-xl);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-5);
}

.dialog__header {
  margin-bottom: var(--gv-space-3);
}

.dialog__title {
  margin: 0;
  font: var(--gv-type-headline-small);
}

.dialog__body {
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-5);
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.dialog-enter-active .dialog__panel,
.dialog-leave-active .dialog__panel {
  transition: transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}

.dialog-enter-from .dialog__panel,
.dialog-leave-to .dialog__panel {
  transform: translateY(8px);
}

@media (prefers-reduced-motion: reduce) {
  .dialog-enter-active,
  .dialog-leave-active,
  .dialog-enter-active .dialog__panel,
  .dialog-leave-active .dialog__panel {
    transition-duration: 1ms;
  }
}
</style>
