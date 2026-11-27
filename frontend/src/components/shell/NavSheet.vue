<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink } from "vue-router";
import IconButton from "@/components/ui/IconButton.vue";
import { useModalHost } from "@/composables/useModalHost";
import NavLink from "./NavLink.vue";
import { navFixed, navGroups } from "./navigation";

/**
 * Full-height navigation sheet for < 840px.
 *
 * The audit (SH-04) found nine destinations with no entry point below 840 and
 * no way to reach settings except through the cookie banner. The sheet renders
 * every destination from the shared table, keeps the current page highlighted
 * through RouterLink's active state, and pins settings / logs at the bottom.
 */
const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const { t } = useI18n();
const root = ref<HTMLDialogElement | null>(null);
const panel = ref<HTMLElement | null>(null);
const { host, refresh: refreshHost, reset: resetHost } = useModalHost();
let pressedOutside = false;

watch(
  () => props.open,
  async (open) => {
    if (open) {
      refreshHost();
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

function close(): void {
  emit("close");
}

function onCancel(event: Event): void {
  event.preventDefault();
  close();
}

function outside(event: MouseEvent): boolean {
  const dialog = root.value;
  if (!dialog || event.target !== dialog) return false;
  const rect = panel.value?.getBoundingClientRect();
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
  if (pressedOutside && outside(event)) close();
  pressedOutside = false;
}

function onAfterLeave(): void {
  resetHost();
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
  <Teleport :to="host">
    <Transition name="nav-sheet" @after-leave="onAfterLeave">
      <dialog
        v-if="open"
        ref="root"
        class="nav-sheet"
        data-testid="nav-sheet"
        :aria-label="t('app.nav.aria')"
        @cancel="onCancel"
        @pointerdown="onPointerDown"
        @pointerup="onPointerUp"
      >
        <section ref="panel" class="nav-sheet__panel" data-testid="nav-sheet-panel">
          <header class="nav-sheet__head">
            <RouterLink to="/browse" class="nav-sheet__brand" @click="close">
              {{ t("app.title") }}
            </RouterLink>
            <IconButton
              name="close"
              :label="t('app.actions.close')"
              data-testid="nav-sheet-close"
              @click="close"
            />
          </header>

          <div class="nav-sheet__scroll">
            <nav
              v-for="group in navGroups"
              :key="group.id"
              class="nav-sheet__group"
              :aria-label="group.headingKey ? t(group.headingKey) : t('app.nav.aria')"
            >
              <p v-if="group.headingKey" class="nav-sheet__heading">
                {{ t(group.headingKey) }}
              </p>
              <NavLink
                v-for="item in group.items"
                :key="item.to"
                :item="item"
                @click="close"
              />
            </nav>
          </div>

          <footer class="nav-sheet__footer">
            <nav class="nav-sheet__group" :aria-label="t('app.nav.aria')">
              <NavLink v-for="item in navFixed" :key="item.to" :item="item" @click="close" />
            </nav>
            <div v-if="$slots.account" class="nav-sheet__account">
              <slot name="account" />
            </div>
          </footer>
        </section>
      </dialog>
    </Transition>
  </Teleport>
</template>

<style scoped>
.nav-sheet {
  position: fixed;
  inset: 0;
  width: 100%;
  max-width: none;
  height: 100%;
  max-height: none;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--gv-color-on-surface);
  overflow: hidden;
  transition-property: display, overlay;
  transition-duration: var(--gv-motion-duration-medium);
  transition-timing-function: var(--gv-motion-ease-standard);
  transition-behavior: allow-discrete;
}

.nav-sheet[open] {
  display: flex;
}

.nav-sheet:modal {
  overscroll-behavior: contain;
}

.nav-sheet::backdrop {
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
  overflow: hidden;
  overscroll-behavior: contain;
}

.nav-sheet__panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(360px, 86vw);
  height: 100%;
  padding: var(--gv-space-2) 0 var(--gv-space-3);
  border-inline-end: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container-low);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-4);
  overscroll-behavior: contain;
}

.nav-sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-topbar);
  padding: 0 var(--gv-space-2) 0 var(--gv-space-5);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.nav-sheet__brand {
  font: var(--gv-type-title-large);
  color: var(--gv-color-primary-text);
}

.nav-sheet__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--gv-space-2) 0;
}

.nav-sheet__group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.nav-sheet__heading {
  margin: var(--gv-space-3) 0 var(--gv-space-1);
  padding: 0 var(--gv-space-5);
  font: var(--gv-type-label-large);
  color: var(--gv-color-primary-text);
}

.nav-sheet__footer {
  flex: none;
  padding-top: var(--gv-space-2);
  border-top: 1px solid var(--gv-color-outline-variant);
}

.nav-sheet__account {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2) var(--gv-space-4) 0;
}

.nav-sheet-enter-active,
.nav-sheet-leave-active {
  transition-property: opacity, display, overlay;
  transition-duration: var(--gv-motion-duration-medium);
  transition-timing-function: var(--gv-motion-ease-standard);
  transition-behavior: allow-discrete;
}

.nav-sheet-enter-active .nav-sheet__panel,
.nav-sheet-leave-active .nav-sheet__panel {
  transition: transform var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.nav-sheet-enter-from,
.nav-sheet-leave-to {
  opacity: 0;
}

.nav-sheet-enter-from .nav-sheet__panel,
.nav-sheet-leave-to .nav-sheet__panel {
  transform: translateX(-100%);
}

@media (prefers-reduced-motion: reduce) {
  .nav-sheet-enter-active,
  .nav-sheet-leave-active,
  .nav-sheet-enter-active .nav-sheet__panel,
  .nav-sheet-leave-active .nav-sheet__panel {
    transition-duration: 1ms;
  }
}
</style>
