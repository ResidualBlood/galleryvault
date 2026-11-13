<script setup lang="ts">
import { ref, watch } from "vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";

const props = defineProps<{
  title: string;
  pageLabel: string;
  jumpValue: number;
  total: number;
  jumpLabel: string;
  jumpPlaceholder: string;
  jumpHint: string;
  closeLabel: string;
  fullscreenLabel: string;
}>();

const emit = defineEmits<{
  close: [];
  jump: [page: number];
  fullscreen: [];
}>();

/**
 * The page text owns the current number; the jump field stays empty until the
 * user types, so the same page is never printed twice (OR-03 / RD-03).
 */
const draft = ref("");
const jumpWrap = ref<HTMLElement | null>(null);

watch(
  () => props.jumpValue,
  () => {
    draft.value = "";
  },
);

function submitJump(): void {
  const value = Number.parseInt(draft.value, 10);
  draft.value = "";
  if (Number.isFinite(value)) emit("jump", value - 1);
}

function focusJump(): void {
  const input = jumpWrap.value?.querySelector("input");
  input?.focus();
  input?.select();
}

defineExpose({ focusJump });
</script>

<template>
  <header class="reader-topbar" data-testid="reader-topbar" data-gv-toolbar>
    <IconButton
      name="back"
      size="lg"
      :label="closeLabel"
      data-testid="reader-close"
      @click="emit('close')"
    />
    <div class="reader-topbar__title-box">
      <p class="reader-topbar__title" :title="title">{{ title }}</p>
    </div>
    <div class="reader-topbar__jump">
      <div ref="jumpWrap" class="reader-topbar__jump-field" data-testid="reader-jump">
        <Input
          v-model="draft"
          type="number"
          size="lg"
          :placeholder="jumpPlaceholder"
          :aria-label="jumpLabel"
          :title="jumpHint"
          @enter="submitJump"
        />
      </div>
      <span class="reader-topbar__page" data-testid="reader-page-label">{{ pageLabel }}</span>
    </div>
    <IconButton
      name="fullscreen"
      size="lg"
      :label="fullscreenLabel"
      data-testid="reader-fullscreen"
      @click="emit('fullscreen')"
    />
  </header>
</template>

<style scoped>
.reader-topbar {
  position: absolute;
  inset: 0 0 auto;
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

/* Flex spacer: the right-hand controls stay flush with the bar padding even
   when the title is hidden at 390 (OR-02 / RD-02). */
.reader-topbar__title-box {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
}

.reader-topbar__title {
  overflow: hidden;
  margin: 0;
  font: var(--gv-type-title-small);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reader-topbar__jump {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.reader-topbar__jump-field {
  width: 72px;
}

.reader-topbar__page {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media (max-width: 599.98px) {
  .reader-topbar__title {
    display: none;
  }
}
</style>
