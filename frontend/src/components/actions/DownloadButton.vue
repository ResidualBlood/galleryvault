<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  useDownloadsStore,
  readDefaultQuality,
  rememberDefaultQuality,
  type DownloadQuality,
} from "@/stores/downloads";
import { useUiStore } from "@/stores/ui";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

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
    <button
      type="button"
      class="dl__button"
      :class="{ 'dl__button--active': busy }"
      :aria-label="t('actions.download')"
      :aria-busy="busy || undefined"
      :disabled="disabled"
      data-testid="download-button"
      :data-status="entry.status"
      @click="start()"
    >
      <span v-if="busy" class="dl__spinner" aria-hidden="true" />
      <svg v-else class="dl__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M11 4h2v9.2l3.3-3.3 1.4 1.4L12 17l-5.7-5.7 1.4-1.4L11 13.2z"
          fill="currentColor"
        />
        <path d="M5 19h14v2H5z" fill="currentColor" />
      </svg>
    </button>

    <button
      type="button"
      class="dl__select"
      :aria-label="t('actions.downloadQuality')"
      :disabled="disabled"
      data-testid="download-quality"
      @click.stop="menuOpen = !menuOpen"
    >
      <span aria-hidden="true">▾</span>
    </button>

    <div v-if="menuOpen" class="dl__menu" role="menu" data-testid="download-quality-menu">
      <button
        type="button"
        class="dl__menu-item"
        :class="{ 'dl__menu-item--selected': quality === 'original' }"
        role="menuitemradio"
        :aria-checked="quality === 'original'"
        data-testid="download-quality-original"
        @click="choose('original')"
      >
        {{ t("actions.qualityOriginal") }}
      </button>
      <button
        type="button"
        class="dl__menu-item"
        :class="{ 'dl__menu-item--selected': quality === 'resample' }"
        role="menuitemradio"
        :aria-checked="quality === 'resample'"
        data-testid="download-quality-resample"
        @click="choose('resample')"
      >
        {{ t("actions.qualityResample") }}
      </button>
    </div>
  </span>
</template>

<style scoped>
.dl {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.dl__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  padding: 0;
  border: 0;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  cursor: pointer;
}

.dl--card .dl__button {
  width: var(--gv-space-6);
  height: var(--gv-space-6);
}

.dl__button:hover {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.dl__button:active {
  background: color-mix(in srgb, currentColor 12%, transparent);
}

.dl__button--active {
  color: var(--gv-color-primary);
}

.dl__icon {
  width: var(--gv-size-icon-lg);
  height: var(--gv-size-icon-lg);
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

.dl__select {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-5);
  height: var(--gv-size-touch);
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.dl--card .dl__select {
  display: none;
}

.dl__menu {
  position: absolute;
  inset-inline-end: 0;
  top: calc(100% + var(--gv-space-1));
  z-index: 31;
  display: flex;
  flex-direction: column;
  min-width: 160px;
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.dl__menu-item {
  min-height: 40px;
  padding: 0 var(--gv-space-3);
  border: 0;
  border-radius: var(--gv-radius-xs);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-label-large);
  text-align: start;
  cursor: pointer;
}

.dl__menu-item:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.dl__menu-item--selected {
  color: var(--gv-color-primary-text);
}
</style>
