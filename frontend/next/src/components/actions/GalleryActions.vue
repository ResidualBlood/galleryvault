<script setup lang="ts">
/**
 * Unified read / favorite / download row for local and online galleries.
 *
 * Three densities share the same behavior and store state:
 *   - card    overlay row revealed on card hover (always visible on touch)
 *   - detail  full row for details pages
 *   - toolbar compact icons for the online reader top bar
 *
 * The host card supplies `favorited` / `favcat` / download fields; afterwards
 * the favorites/downloads stores are the single source of truth. Long press
 * on the row opens a bottom sheet (mobile quick actions).
 */
import { computed, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Sheet from "@/components/ui/Sheet.vue";
import FavButton from "./FavButton.vue";
import DownloadButton from "./DownloadButton.vue";
import { useFavoritesStore } from "@/stores/favorites";
import { useDownloadsStore } from "@/stores/downloads";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

const props = withDefaults(
  defineProps<{
    gid: number;
    token: string;
    title?: string;
    source?: "local" | "online";
    density?: "card" | "detail" | "toolbar";
    favorited?: boolean;
    favcat?: number | null;
    inLibrary?: boolean;
    downloadStatus?: string | null;
    downloadCurrentPage?: number | null;
    downloadTotalPages?: number | null;
    disabled?: boolean;
    /** Hosts that own their own read CTA (reader toolbar, detail rows) pass false. */
    showRead?: boolean;
  }>(),
  {
    title: "",
    source: "local",
    density: "card",
    favorited: false,
    favcat: null,
    inLibrary: false,
    downloadStatus: null,
    downloadCurrentPage: 0,
    downloadTotalPages: null,
    disabled: false,
    showRead: true,
  },
);

const emit = defineEmits<{ read: [] }>();

const { t } = useI18n();
const favorites = useFavoritesStore();
const downloads = useDownloadsStore();

favorites.ensure(props.gid, { favorited: props.favorited, favcat: props.favcat });
downloads.ensure(props.gid, {
  status: props.downloadStatus,
  currentPage: props.downloadCurrentPage,
  totalPages: props.downloadTotalPages,
  inLibrary: props.inLibrary,
});

const sheetOpen = ref(false);
let pressTimer: ReturnType<typeof setTimeout> | null = null;
let suppressClick = false;

const downloadEntry = computed(() => downloads.get(props.gid));

const downloadBadge = computed<{ label: string; tone: string } | null>(() => {
  const entry = downloadEntry.value;
  if (entry.inLibrary || entry.status === "success") {
    return { label: t("actions.downloadInLibrary"), tone: "success" };
  }
  if (entry.status === "downloading") {
    const current = Math.max(0, entry.currentPage);
    const total = entry.totalPages;
    return {
      label:
        total && total > 0
          ? t("actions.downloadActive", { current, total })
          : t("actions.downloadActiveNoTotal", { current }),
      tone: "primary",
    };
  }
  if (entry.status === "queued") return { label: t("actions.downloadQueued"), tone: "tertiary" };
  if (entry.status === "failed") return { label: t("actions.downloadFailed"), tone: "error" };
  return null;
});

function clearPress(): void {
  if (pressTimer !== null) {
    clearTimeout(pressTimer);
    pressTimer = null;
  }
}

function startPress(event: PointerEvent): void {
  if (props.disabled || event.button !== 0) return;
  clearPress();
  pressTimer = setTimeout(() => {
    pressTimer = null;
    suppressClick = true;
    sheetOpen.value = true;
  }, 520);
}

function captureClick(event: MouseEvent): void {
  if (!suppressClick) return;
  suppressClick = false;
  event.preventDefault();
  event.stopPropagation();
}

function read(): void {
  sheetOpen.value = false;
  emit("read");
}

onBeforeUnmount(clearPress);
</script>

<template>
  <div
    class="gallery-actions"
    :class="[`gallery-actions--${density}`, `gallery-actions--${source}`]"
    data-testid="gallery-actions"
    :data-density="density"
    :data-gid="gid"
    @pointerdown="startPress"
    @pointerup="clearPress"
    @pointercancel="clearPress"
    @pointerleave="clearPress"
    @click.capture="captureClick"
  >
    <Button
      v-if="showRead && density === 'detail'"
      variant="filled"
      size="compact"
      :disabled="disabled"
      data-testid="action-read"
      @click="read"
    >
      {{ t("actions.read") }}
    </Button>
    <button
      v-else-if="showRead"
      type="button"
      class="gallery-actions__read"
      :aria-label="t('actions.read')"
      :disabled="disabled"
      data-testid="action-read"
      @click="read"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15.5H6.5A2.5 2.5 0 0 0 4 21z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          stroke-linejoin="round"
        />
        <path d="M7 7h9M7 10.5h9" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
    </button>

    <FavButton
      :gid="gid"
      :token="token"
      :favorited="favorited"
      :favcat="favcat"
      :density="density"
      :disabled="disabled"
    />

    <DownloadButton
      :gid="gid"
      :token="token"
      :title="title"
      :status="downloadStatus"
      :current-page="downloadCurrentPage"
      :total-pages="downloadTotalPages"
      :in-library="inLibrary"
      :density="density"
      :disabled="disabled"
    />

    <span
      v-if="downloadBadge"
      class="gallery-actions__badge"
      :class="`gallery-actions__badge--${downloadBadge.tone}`"
      data-testid="download-badge"
      :data-status="downloadEntry.status"
    >
      {{ downloadBadge.label }}
    </span>


    <Sheet
      :open="sheetOpen"
      :title="t('actions.actions')"
      testid="action-sheet"
      @close="sheetOpen = false"
    >
      <div class="gallery-actions__sheet">
        <Button v-if="showRead" variant="filled" :disabled="disabled" data-testid="sheet-read" @click="read">
          {{ t("actions.read") }}
        </Button>
        <div class="gallery-actions__sheet-row">
          <FavButton
            :gid="gid"
            :token="token"
            :favorited="favorited"
            :favcat="favcat"
            density="detail"
            :disabled="disabled"
          />
          <DownloadButton
            :gid="gid"
            :token="token"
            :title="title"
            :status="downloadStatus"
            :current-page="downloadCurrentPage"
            :total-pages="downloadTotalPages"
            :in-library="inLibrary"
            density="detail"
            :disabled="disabled"
          />
          <span
            v-if="downloadBadge"
            class="gallery-actions__badge"
            :class="`gallery-actions__badge--${downloadBadge.tone}`"
          >
            {{ downloadBadge.label }}
          </span>
        </div>
      </div>
    </Sheet>
  </div>
</template>

<style scoped>
.gallery-actions {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
}

.gallery-actions--card {
  justify-content: flex-end;
  gap: 0;
  padding: var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: color-mix(in srgb, var(--gv-color-surface) 78%, transparent);
  box-shadow: var(--gv-elev-1);
  opacity: 0;
  transition: opacity var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

:global(.gallery-card:hover .gallery-actions--card),
.gallery-actions--card:focus-within {
  opacity: 1;
}

@media (hover: none), (max-width: 599px) {
  .gallery-actions--card {
    opacity: 1;
  }
}

.gallery-actions__read {
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

.gallery-actions--card .gallery-actions__read {
  width: var(--gv-space-6);
  height: var(--gv-space-6);
}

.gallery-actions__read:hover {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.gallery-actions__read svg {
  width: var(--gv-size-icon-lg);
  height: var(--gv-size-icon-lg);
}

.gallery-actions__badge {
  display: inline-flex;
  align-items: center;
  height: var(--gv-size-icon-md);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-xs);
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.gallery-actions__badge--success {
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
}

.gallery-actions__badge--primary {
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.gallery-actions__badge--tertiary {
  background: var(--gv-color-tertiary-container);
  color: var(--gv-color-on-tertiary-container);
}

.gallery-actions__badge--error {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.gallery-actions--toolbar .gallery-actions__badge {
  display: none;
}

.gallery-actions__sheet {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.gallery-actions__sheet-row {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
}
</style>
