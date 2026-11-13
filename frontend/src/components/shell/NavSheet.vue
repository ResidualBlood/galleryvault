<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink } from "vue-router";
import IconButton from "@/components/ui/IconButton.vue";
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
const panel = ref<HTMLElement | null>(null);
const triggers = () => document.documentElement.classList;

function close(): void {
  emit("close");
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && props.open) close();
}

watch(
  () => props.open,
  async (open) => {
    triggers().toggle("gv-nav-sheet-open", open);
    if (open) {
      await nextTick();
      panel.value?.focus();
    }
  },
);

onMounted(() => document.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
  triggers().remove("gv-nav-sheet-open");
});
</script>

<template>
  <Teleport to="body">
    <Transition name="nav-sheet">
      <div v-if="open" class="nav-sheet" data-testid="nav-sheet">
        <div class="nav-sheet__scrim" @click="close" />
        <section
          ref="panel"
          class="nav-sheet__panel"
          role="dialog"
          aria-modal="true"
          :aria-label="t('app.nav.aria')"
          data-testid="nav-sheet-panel"
          tabindex="-1"
        >
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
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.nav-sheet {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
}

.nav-sheet__scrim {
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--gv-color-scrim) 60%, transparent);
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

:global(html.gv-nav-sheet-open),
:global(html.gv-nav-sheet-open body) {
  overflow: hidden;
}

.nav-sheet-enter-active,
.nav-sheet-leave-active {
  transition: opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
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
