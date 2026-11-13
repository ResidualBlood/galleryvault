<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useFavoritesStore, parseFavcat, readDefaultFavcat } from "@/stores/favorites";
import { useUiStore } from "@/stores/ui";
import FavPicker from "./FavPicker.vue";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

const props = withDefaults(
  defineProps<{
    gid: number;
    token: string;
    favorited?: boolean;
    favcat?: number | null;
    density?: "card" | "detail" | "toolbar";
    disabled?: boolean;
  }>(),
  {
    favorited: false,
    favcat: null,
    density: "card",
    disabled: false,
  },
);

const { t } = useI18n();
const store = useFavoritesStore();
const ui = useUiStore();

store.ensure(props.gid, { favorited: props.favorited, favcat: props.favcat });

const pickerOpen = ref(false);
const menuOpen = ref(false);
let pressTimer: ReturnType<typeof setTimeout> | null = null;

const entry = computed(() => store.get(props.gid));
const active = computed(() => entry.value.favorited);
const activeFavcat = computed(() => parseFavcat(entry.value.favcat) ?? 0);
const pending = computed(() => entry.value.pending);

const heartStyle = computed(() =>
  active.value ? { color: `var(--gv-favcat-${activeFavcat.value})` } : undefined,
);

const label = computed(() =>
  active.value ? t("actions.favoriteSelect") : t("actions.favorite"),
);

watch(
  () => [props.favorited, props.favcat] as const,
  ([favorited, favcat]) => {
    store.ensure(props.gid);
    const currentEntry = store.get(props.gid);
    if (favorited && !currentEntry.favorited) {
      store.applyFavorite(props.gid, parseFavcat(favcat) ?? 0);
    }
  },
);

watch(
  () => props.gid,
  (gid) => {
    store.ensure(gid, { favorited: props.favorited, favcat: props.favcat });
    menuOpen.value = false;
    pickerOpen.value = false;
  },
);

function clearPress(): void {
  if (pressTimer !== null) {
    clearTimeout(pressTimer);
    pressTimer = null;
  }
}

function startPress(event: PointerEvent): void {
  if (props.disabled || props.density === "card" || event.button !== 0) return;
  clearPress();
  pressTimer = setTimeout(() => {
    pressTimer = null;
    openPicker();
  }, 520);
}

function openPicker(): void {
  menuOpen.value = false;
  pickerOpen.value = true;
}

async function addDefault(): Promise<void> {
  const favcat = readDefaultFavcat();
  if (favcat === null) {
    openPicker();
    return;
  }
  try {
    const result = await store.add(props.gid, props.token, favcat);
    if (result.ok) ui.success(t("actions.favoriteAdded"));
    else ui.error(t("actions.favoriteFailed"));
  } catch {
    ui.error(t("actions.favoriteFailed"));
  }
}

function onClick(event: MouseEvent): void {
  if (props.disabled) return;
  if (event.detail === 0 && pending.value) return;
  if (active.value) {
    menuOpen.value = !menuOpen.value;
    return;
  }
  void addDefault();
}

function onContextMenu(event: MouseEvent): void {
  event.preventDefault();
  if (!props.disabled) openPicker();
}

async function remove(): Promise<void> {
  menuOpen.value = false;
  try {
    const result = await store.remove(props.gid);
    if (result.ok) ui.success(t("actions.favoriteRemoved"));
    else ui.error(t("actions.favoriteRemoveFailed"));
  } catch {
    ui.error(t("actions.favoriteRemoveFailed"));
  }
}

function move(): void {
  openPicker();
}

onBeforeUnmount(clearPress);
</script>

<template>
  <span class="fav" :class="`fav--${density}`" :data-testid="`fav-${gid}`">
    <button
      type="button"
      class="fav__button"
      :class="{ 'fav__button--active': active }"
      :aria-label="label"
      :aria-pressed="active"
      :aria-busy="pending || undefined"
      :disabled="disabled"
      data-testid="fav-button"
      :data-favcat="active ? activeFavcat : undefined"
      @click="onClick"
      @contextmenu="onContextMenu"
      @pointerdown="startPress"
      @pointerup="clearPress"
      @pointercancel="clearPress"
      @pointerleave="clearPress"
    >
      <span v-if="pending" class="fav__spinner" aria-hidden="true" />
      <svg
        v-else
        class="fav__heart"
        :class="{ 'fav__heart--active': active }"
        :style="heartStyle"
        viewBox="0 0 24 24"
        aria-hidden="true"
        data-testid="fav-heart"
        :data-favcat="active ? activeFavcat : undefined"
      >
        <path
          v-if="active"
          d="M12 21s-7.5-4.6-9.6-8.2C.7 9.5 2.4 5.5 6.1 5.1c2-.2 3.8.8 4.9 2.4 1.1-1.6 2.9-2.6 4.9-2.4 3.7.4 5.4 4.4 3.7 7.7C19.5 16.4 12 21 12 21z"
          fill="currentColor"
        />
        <path
          v-else
          d="M12 20.2s-7-4.3-8.9-7.7C1.6 9.8 3.1 6.4 6.4 6c1.8-.2 3.4.7 4.5 2.2l1.1 1.5 1.1-1.5C14.2 6.7 15.8 5.8 17.6 6c3.3.4 4.8 3.8 3.3 6.5-1.9 3.4-8.9 7.7-8.9 7.7z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <button
      type="button"
      class="fav__select"
      :aria-label="t('actions.favoriteSelect')"
      :disabled="disabled"
      data-testid="fav-select"
      @click.stop="openPicker"
    >
      <span aria-hidden="true">▾</span>
    </button>

    <div v-if="menuOpen" class="fav__menu" role="menu" data-testid="fav-menu">
      <button type="button" class="fav__menu-item" role="menuitem" data-testid="fav-move" @click="move">
        {{ t("actions.favoriteMove") }}
      </button>
      <button
        type="button"
        class="fav__menu-item fav__menu-item--danger"
        role="menuitem"
        data-testid="fav-remove"
        @click="remove"
      >
        {{ t("actions.favoriteRemove") }}
      </button>
    </div>

    <FavPicker
      :open="pickerOpen"
      :gid="gid"
      :token="token"
      :favorited="active"
      :favcat="entry.favcat"
      :note="entry.note"
      :disabled="disabled"
      @close="pickerOpen = false"
    />
  </span>
</template>

<style scoped>
.fav {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.fav__button {
  position: relative;
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

.fav--card .fav__button {
  width: var(--gv-space-6);
  height: var(--gv-space-6);
}

.fav__button:hover {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.fav__button:active {
  background: color-mix(in srgb, currentColor 12%, transparent);
}

.fav__button--active {
  color: inherit;
}

.fav__heart {
  width: var(--gv-size-icon-lg);
  height: var(--gv-size-icon-lg);
}

.fav__heart--active {
  filter: drop-shadow(0 0 var(--gv-space-xs) var(--gv-color-surface));
}

.fav__spinner {
  width: var(--gv-size-icon-md);
  height: var(--gv-size-icon-md);
  border: var(--gv-state-focus-ring-width) solid
    color-mix(in srgb, var(--gv-color-on-surface-variant) 30%, transparent);
  border-top-color: var(--gv-color-primary);
  border-radius: var(--gv-radius-full);
  animation: fav-spin var(--gv-motion-duration-long) linear infinite;
}

@keyframes fav-spin {
  to {
    transform: rotate(360deg);
  }
}

.fav__select {
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

.fav--card .fav__select {
  display: none;
}

.fav__menu {
  position: absolute;
  inset-inline-end: 0;
  top: calc(100% + var(--gv-space-1));
  z-index: 31;
  display: flex;
  flex-direction: column;
  min-width: 180px;
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.fav__menu-item {
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

.fav__menu-item:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.fav__menu-item--danger {
  color: var(--gv-color-error);
}
</style>
