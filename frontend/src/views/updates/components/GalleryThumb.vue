<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { coverSrc } from "@/views/updates/url";

const props = withDefaults(
  defineProps<{
    src?: string | null;
    alt?: string;
    size?: "card" | "row";
  }>(),
  {
    src: "",
    alt: "",
    size: "row",
  },
);

const { t } = useI18n();
const failed = ref(false);
const safe = computed(() => coverSrc(props.src));

watch(
  () => props.src,
  () => {
    failed.value = false;
  },
);
</script>

<template>
  <span class="thumb" :class="`thumb--${props.size}`">
    <img
      v-if="safe && !failed"
      :src="safe"
      :alt="props.alt"
      loading="lazy"
      @error="failed = true"
    />
    <span v-else class="thumb__empty">{{ t("maintenance.shared.noCover") }}</span>
  </span>
</template>

<style scoped>
.thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
}

.thumb--card {
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
}

.thumb--row {
  width: 56px;
  height: 72px;
  flex: 0 0 auto;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb__empty {
  padding: var(--gv-space-1);
  font: var(--gv-type-label-small);
  text-align: center;
}
</style>
