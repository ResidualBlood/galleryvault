<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";

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
    testid: "sheet",
  },
);

const emit = defineEmits<{ close: [] }>();

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
    <Transition name="sheet">
      <div v-if="open" class="sheet">
        <div class="sheet__scrim" @click="requestClose" />
        <section
          class="sheet__panel"
          role="dialog"
          aria-modal="true"
          :data-testid="testid"
          tabindex="-1"
        >
          <div class="sheet__handle" aria-hidden="true" />
          <header v-if="title" class="sheet__header">
            <h2 class="sheet__title">{{ title }}</h2>
          </header>
          <div class="sheet__body"><slot /></div>
          <footer v-if="$slots.footer" class="sheet__footer"><slot name="footer" /></footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.sheet__scrim {
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
}

.sheet__panel {
  position: relative;
  width: min(640px, 100vw);
  max-height: 90vh;
  overflow: auto;
  padding: var(--gv-space-3) var(--gv-space-4) var(--gv-space-5);
  border-radius: var(--gv-radius-xl) var(--gv-radius-xl) 0 0;
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-4);
}

.sheet__handle {
  width: 32px;
  height: 4px;
  margin: 0 auto var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-outline);
}

.sheet__header {
  margin-bottom: var(--gv-space-2);
}

.sheet__title {
  margin: 0;
  font: var(--gv-type-title-medium);
}

.sheet__body {
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.sheet__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-4);
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity var(--gv-motion-duration-long) var(--gv-motion-ease-standard);
}

.sheet-enter-active .sheet__panel,
.sheet-leave-active .sheet__panel {
  transition: transform var(--gv-motion-duration-long) var(--gv-motion-ease-standard);
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}

.sheet-enter-from .sheet__panel,
.sheet-leave-to .sheet__panel {
  transform: translateY(100%);
}

@media (min-width: 840px) {
  .sheet {
    align-items: center;
    justify-content: flex-end;
  }

  .sheet__panel {
    height: 100%;
    max-height: none;
    width: min(420px, 100vw);
    border-radius: var(--gv-radius-xl) 0 0 var(--gv-radius-xl);
  }

  .sheet-enter-from .sheet__panel,
  .sheet-leave-to .sheet__panel {
    transform: translateX(100%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .sheet-enter-active,
  .sheet-leave-active,
  .sheet-enter-active .sheet__panel,
  .sheet-leave-active .sheet__panel {
    transition-duration: 1ms;
  }
}
</style>
