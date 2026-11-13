<script lang="ts">
import type { Component, InjectionKey, Ref, VNode } from "vue";

export interface ToolbarOverflowEntry {
  id: number;
  component: Component;
}

export interface ToolbarContext {
  /** True below the 600px compact breakpoint. */
  compact: Ref<boolean>;
  register: (id: number, render: () => VNode[]) => void;
  unregister: (id: number) => void;
}

export const TOOLBAR_CONTEXT: InjectionKey<ToolbarContext> = Symbol("gvToolbar");
</script>

<script setup lang="ts">
import { computed, defineComponent, markRaw, onBeforeUnmount, onMounted, provide, ref } from "vue";
import { useI18n } from "vue-i18n";
import Menu from "./Menu.vue";
import { provideControlSize, resolveControlSize, type ControlSizeProp } from "./control-size";
import { ensureLayoutMessages } from "./i18n/layout";

ensureLayoutMessages();

const props = withDefaults(
  defineProps<{
    /**
     * Control ladder step for every descendant control. `lg` / `md` / `sm` are
     * the working steps; the legacy `compact` / `small` aliases map to `sm`.
     */
    size?: ControlSizeProp;
    sticky?: boolean;
    moreLabel?: string;
    moreTestid?: string;
    testid?: string;
  }>(),
  {
    size: "lg",
    sticky: false,
    moreLabel: "",
    moreTestid: "gv-toolbar-more",
    testid: "gv-toolbar",
  },
);

const { t } = useI18n();

const controlSize = provideControlSize(computed(() => resolveControlSize(props.size)));

const compact = ref(false);
const overflow = ref<ToolbarOverflowEntry[]>([]);
let media: MediaQueryList | null = null;

function syncCompact(event?: MediaQueryListEvent): void {
  if (event) {
    compact.value = !event.matches;
    return;
  }
  if (media) compact.value = !media.matches;
}

function register(id: number, render: () => import("vue").VNode[]): void {
  if (overflow.value.some((entry) => entry.id === id)) return;
  const component = markRaw(
    defineComponent({
      name: "GvToolbarOverflowGroup",
      setup() {
        return () => render();
      },
    }),
  );
  overflow.value = [...overflow.value, { id, component }];
}

function unregister(id: number): void {
  overflow.value = overflow.value.filter((entry) => entry.id !== id);
}

provide(TOOLBAR_CONTEXT, { compact, register, unregister });

onMounted(() => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  media = window.matchMedia("(min-width: 600px)");
  syncCompact();
  media.addEventListener?.("change", syncCompact);
});

onBeforeUnmount(() => {
  media?.removeEventListener?.("change", syncCompact);
});
</script>

<template>
  <div
    class="toolbar"
    :class="{ 'toolbar--sticky': sticky }"
    data-gv-toolbar
    :data-size="controlSize"
    :data-testid="testid"
  >
    <slot />
    <Menu
      v-if="compact && overflow.length"
      class="toolbar__more"
      :label="moreLabel || t('kit.toolbar.more')"
      :testid="moreTestid"
      icon="more"
    >
      <div class="toolbar__overflow">
        <component :is="entry.component" v-for="entry in overflow" :key="entry.id" />
      </div>
    </Menu>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-4);
  width: 100%;
  min-height: var(--gv-size-control-lg);
}

.toolbar--sticky {
  position: sticky;
  top: 0;
  z-index: 12;
  padding-block: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface);
}

.toolbar__overflow {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--gv-space-3);
}

@media (max-width: 599.98px) {
  .toolbar__more {
    margin-inline-start: auto;
  }
}
</style>
