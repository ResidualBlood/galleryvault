<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, useSlots } from "vue";
import { TOOLBAR_CONTEXT, type ToolbarContext } from "./Toolbar.vue";

const props = withDefaults(
  defineProps<{
    /** Push this group to the trailing edge of the toolbar. */
    end?: boolean;
    /** Hide below 600px and move the group into the toolbar "More" menu. */
    collapsible?: boolean;
    /** Optional label used by the overflow menu. */
    label?: string;
    testid?: string;
  }>(),
  { end: false, collapsible: false, label: "", testid: "" },
);

const toolbar = inject<ToolbarContext | null>(TOOLBAR_CONTEXT, null);
const slots = useSlots();
const id = Math.random();

const hidden = computed(() => props.collapsible && Boolean(toolbar?.compact.value));

onMounted(() => {
  if (props.collapsible && toolbar) {
    toolbar.register(id, () => slots.default?.() ?? []);
  }
});

onBeforeUnmount(() => {
  toolbar?.unregister(id);
});
</script>

<template>
  <div
    v-if="!hidden"
    class="toolbar-group"
    :class="{ 'toolbar-group--end': end }"
    data-gv-toolbar-group
    :data-end="end ? 'true' : undefined"
    :data-label="label || undefined"
    :data-testid="testid || undefined"
  >
    <slot />
  </div>
</template>

<style scoped>
.toolbar-group {
  display: flex;
  flex: none;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.toolbar-group--end {
  margin-inline-start: auto;
}
</style>
