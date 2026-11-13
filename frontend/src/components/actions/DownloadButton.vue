<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import {
  useDownloadsStore,
  readDefaultQuality,
  rememberDefaultQuality,
  type DownloadQuality,
} from "@/stores/downloads";
import { useUiStore } from "@/stores/ui";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

/**
 * Download control with the quality menu.
 *
 * `card` / `toolbar` render one icon-only button; `detail` renders a split
 * button (icon + label | chevron) sized on the same `lg` step as the read CTA.
 */
const props = withDefaults(
  defineProps<{
    gid: number;
    token: string;
    title?: string;
    status?: string | null;
    currentPage?: number | null;
    totalPages?: number | null;
    inLibrary?: boolean;
    density?: "card" | "detail" | "toolbar";
    disabled?: boolean;
  }>(),
  {
    title: "",
    status: null,
    currentPage: 0,
    totalPages: null,
    inLibrary: false,
    density: "card",
    disabled: false,
  },
);

const { t } = useI18n();
const downloads = useDownloadsStore();
const ui = useUiStore();

const menuOpen = ref(false);
const entry = computed(() => downloads.get(props.gid));
const busy = computed(
  () => entry.value.pending || entry.value.status === "queued" || entry.value.status === "downloading",
);
const quality = ref<DownloadQuality>(readDefaultQuality());

function seed(): void {
  downloads.watch(props.gid, {
    status: props.status,
    currentPage: props.currentPage,
    totalPages: props.totalPages,
    inLibrary: props.inLibrary,
  });
}

seed();

watch(
  () => props.gid,
  (_gid, previous) => {
    if (typeof previous === "number") downloads.unwatch(previous);
    seed();
  },
);

watch(
  () => [props.status, props.inLibrary, props.currentPage, props.totalPages] as const,
  () => {
    downloads.applySeed(props.gid, {
      status: props.status,
      currentPage: props.currentPage,
      totalPages: props.totalPages,
      inLibrary: props.inLibrary,
    });
  },
);

onBeforeUnmount(() => downloads.unwatch(props.gid));

function start(selected: DownloadQuality = quality.value): void {
  if (props.disabled || busy.value) return;
  if (entry.value.inLibrary || entry.value.status === "success") {
    ui.info(t("actions.downloadInLibrary"));
    return;
  }
  quality.value = selected;
  void downloads
    .enqueue(props.gid, props.token, { title: props.title, quality: selected })
    .then((queued) => {
      if (queued) ui.success(t("actions.downloadQueuedToast"));
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      ui.error(t("actions.downloadFailedToast", { message }));
    });
}

function choose(next: DownloadQuality): void {
  quality.value = rememberDefaultQuality(next);
  menuOpen.value = false;
  ui.success(
    t("actions.qualitySaved", {
      quality: t(next === "original" ? "actions.qualityOriginal" : "actions.qualityResample"),
    }),
  );
  if (!busy.value && !entry.value.inLibrary) start(quality.value);
}
</script>

<template>
  <span class="dl" :class="`dl--${density}`">
    <Button
      class="dl__main"
      :class="{ 'dl__main--busy': busy }"
      :variant="density === 'detail' ? 'outlined' : 'text'"
      :size="density === 'card' ? 'sm' : 'lg'"
      :aria-label="t('actions.download')"
      :aria-busy="busy || undefined"
      :disabled="disabled"
      data-testid="download-button"
      :data-status="entry.status"
      @click="start()"
    >
      <template #leading>
        <span v-if="busy" class="dl__spinner" aria-hidden="true" />
        <Icon
          v-else
          class="dl__icon"
          name="downloads"
          :size="density === 'card' ? 'dense' : 'md'"
        />
      </template>
      <span v-if="density === 'detail'" class="dl__label">{{ t("actions.download") }}</span>
    </Button>

    <Button
      v-if="density === 'detail'"
      class="dl__toggle"
      variant="outlined"
      size="lg"
      :aria-label="t('actions.downloadQuality')"
      :disabled="disabled"
      data-testid="download-quality"
      @click.stop="menuOpen = !menuOpen"
    >
      <Icon name="chevron-down" size="md" />
    </Button>

    <div v-if="menuOpen" class="dl__menu" role="menu" data-testid="download-quality-menu">
      <Button
        variant="text"
        size="md"
        class="dl__menu-item"
        :class="{ 'dl__menu-item--selected': quality === 'original' }"
        role="menuitemradio"
        :aria-checked="quality === 'original'"
        data-testid="download-quality-original"
        @click="choose('original')"
      >
        {{ t("actions.qualityOriginal") }}
      </Button>
      <Button
        variant="text"
        size="md"
        class="dl__menu-item"
        :class="{ 'dl__menu-item--selected': quality === 'resample' }"
        role="menuitemradio"
        :aria-checked="quality === 'resample'"
        data-testid="download-quality-resample"
        @click="choose('resample')"
      >
        {{ t("actions.qualityResample") }}
      </Button>
    </div>
  </span>
</template>

<style scoped>
.dl {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.dl__main {
  position: relative;
}

/* Split button: square inner edge, divider from the toggle's left border. */
.dl--detail .dl__main {
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
  border-right-width: 0;
}

.dl__toggle {
  width: var(--gv-size-control-lg);
  padding: 0;
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
}

.dl--card .dl__main {
  width: var(--gv-size-control-sm);
  padding: 0;
}

.dl--toolbar .dl__main {
  width: var(--gv-size-control-lg);
  padding: 0;
}

/* Icon-only densities read as a neutral glyph; only the busy state adds colour. */
.dl--card .dl__main,
.dl--toolbar .dl__main {
  color: var(--gv-color-on-surface-variant);
}

.dl__main--busy {
  color: var(--gv-color-primary);
}

.dl__label {
  white-space: nowrap;
}

/* The glyph stays neutral like the favourite heart (C06); only the label and
   the busy state carry the accent colour. Disabled falls back to the button
   colour so the layered disabled treatment still applies. */
.dl__icon {
  color: var(--gv-color-on-surface-variant);
}

.dl__main:disabled .dl__icon {
  color: inherit;
}

.dl__spinner {
  width: var(--gv-size-icon-md);
  height: var(--gv-size-icon-md);
  border: var(--gv-state-focus-ring-width) solid
    color-mix(in srgb, var(--gv-color-primary) 30%, transparent);
  border-top-color: var(--gv-color-primary);
  border-radius: var(--gv-radius-full);
  animation: dl-spin var(--gv-motion-duration-long) linear infinite;
}

@keyframes dl-spin {
  to {
    transform: rotate(360deg);
  }
}

.dl__menu {
  position: absolute;
  inset-inline-end: 0;
  top: calc(100% + var(--gv-space-1));
  z-index: 31;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 160px;
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.dl__menu-item {
  justify-content: flex-start;
  width: 100%;
}

.dl__menu-item--selected {
  color: var(--gv-color-primary-text);
}

@media (max-width: 599.98px) {
  .dl--detail .dl__main {
    width: var(--gv-size-control-lg);
    padding: 0;
  }

  .dl--detail .dl__label {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dl__spinner {
    animation-duration: 2s;
  }
}
</style>
