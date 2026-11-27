<script setup lang="ts">
/**
 * Icon-only grid / list / table switch for one page (DESIGN.md C18).
 *
 * It is a segmented control built from the shared IconButton: every segment
 * uses the current control ladder step, so the toggle sits on the same height
 * and centre line as the toolbar's search field and buttons. Each segment has
 * an `aria-label`, `title` and `aria-pressed`; the table segment disappears
 * below 600px (the mode itself falls back to list).
 */
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import IconButton from "@/components/ui/IconButton.vue";
import { ensureCollectionMessages } from "./collection-messages";
import { VIEW_MODES, type ViewMode } from "@/composables/useViewMode";

ensureCollectionMessages();

const props = withDefaults(
  defineProps<{
    modelValue: ViewMode;
    /** Modes the page currently offers (narrow screens drop `table`). */
    options?: readonly ViewMode[];
    testid?: string;
  }>(),
  { options: () => VIEW_MODES, testid: "view-mode-toggle" },
);

const emit = defineEmits<{
  "update:modelValue": [mode: ViewMode];
  change: [mode: ViewMode];
}>();

const { t } = useI18n();

const modes = computed(() => props.options);

const ICONS: Record<ViewMode, "grid" | "list" | "table"> = {
  grid: "grid",
  list: "list",
  table: "table",
};

function label(mode: ViewMode): string {
  return t(`collection.view.${mode}`);
}

function select(mode: ViewMode): void {
  if (mode === props.modelValue) return;
  emit("update:modelValue", mode);
  emit("change", mode);
}
</script>

<template>
  <div
    class="view-mode-toggle"
    role="group"
    :aria-label="t('collection.view.label')"
    :data-testid="testid"
    :data-mode="modelValue"
  >
    <IconButton
      v-for="mode in modes"
      :key="mode"
      :name="ICONS[mode]"
      :label="label(mode)"
      size="default"
      :selected="mode === modelValue"
      :data-view-mode="mode"
      @click="select(mode)"
    />
  </div>
</template>

<style scoped>
.view-mode-toggle {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
}
</style>
