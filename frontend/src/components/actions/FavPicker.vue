<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Sheet from "@/components/ui/Sheet.vue";
import FavPickerPanel from "./FavPickerPanel.vue";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

withDefaults(
  defineProps<{
    open: boolean;
    gid: number;
    token: string;
    favorited: boolean;
    favcat: number | null;
    note?: string | null;
    disabled?: boolean;
  }>(),
  { note: "", disabled: false },
);

const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();

const compact = ref(false);
let media: MediaQueryList | null = null;

function sync(event?: MediaQueryListEvent): void {
  compact.value = event ? event.matches : Boolean(media?.matches);
}

onMounted(() => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  media = window.matchMedia("(max-width: 599px)");
  sync();
  media.addEventListener("change", sync);
});

onBeforeUnmount(() => {
  media?.removeEventListener("change", sync);
});
</script>

<template>
  <Sheet
    v-if="compact"
    :open="open"
    :title="t('actions.favoriteSelect')"
    testid="fav-sheet"
    @close="emit('close')"
  >
    <FavPickerPanel
      v-if="open"
      :gid="gid"
      :token="token"
      :favorited="favorited"
      :favcat="favcat"
      :note="note"
      :disabled="disabled"
      :heading="false"
      @done="emit('close')"
    />
  </Sheet>

  <div v-else-if="open" class="fav-picker">
    <div class="fav-picker__scrim" @click="emit('close')" />
    <div class="fav-picker__panel" role="dialog" data-testid="fav-picker">
      <FavPickerPanel
        :gid="gid"
        :token="token"
        :favorited="favorited"
        :favcat="favcat"
        :note="note"
        :disabled="disabled"
        @done="emit('close')"
      />
    </div>
  </div>
</template>

<style scoped>
.fav-picker {
  position: absolute;
  inset-inline-end: 0;
  top: calc(100% + var(--gv-space-1));
  z-index: 31;
}

.fav-picker__scrim {
  position: fixed;
  inset: 0;
  z-index: -1;
}

.fav-picker__panel {
  width: min(360px, calc(100vw - var(--gv-space-6)));
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-3);
}
</style>
