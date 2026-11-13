<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import { useFavoritesStore, parseFavcat, readDefaultFavcat } from "@/stores/favorites";
import { useUiStore } from "@/stores/ui";
import FavPicker from "./FavPicker.vue";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

/**
 * Favourite control.
 *
 * `card` / `toolbar` render one icon-only button; `detail` renders a split
 * button (icon + label | chevron) whose two segments share the `lg` ladder
 * height, so the detail action row stays exactly as tall as the read button.
 */
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
    <Button
      class="fav__main"
      :class="{ 'fav__main--active': active }"
      :variant="density === 'detail' ? 'outlined' : 'text'"
      :size="density === 'card' ? 'sm' : 'lg'"
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
      <template #leading>
        <span v-if="pending" class="fav__spinner" aria-hidden="true" />
        <Icon
          v-else
          class="fav__heart"
          :class="{ 'fav__heart--active': active }"
          :style="heartStyle"
          :name="active ? 'favorite' : 'favorite-outline'"
          :size="density === 'card' ? 'dense' : 'md'"
          data-testid="fav-heart"
          :data-favcat="active ? activeFavcat : undefined"
        />
      </template>
      <span v-if="density === 'detail'" class="fav__label">{{ label }}</span>
    </Button>

    <Button
      v-if="density === 'detail'"
      class="fav__toggle"
      variant="outlined"
      size="lg"
      :aria-label="t('actions.favoriteSelect')"
      :disabled="disabled"
      data-testid="fav-select"
      @click.stop="openPicker"
    >
      <Icon name="chevron-down" size="md" />
    </Button>

    <div v-if="menuOpen" class="fav__menu" role="menu" data-testid="fav-menu">
      <Button
        variant="text"
        size="md"
        class="fav__menu-item"
        role="menuitem"
        data-testid="fav-move"
        @click="move"
      >
        {{ t("actions.favoriteMove") }}
      </Button>
      <Button
        variant="text"
        size="md"
        danger
        class="fav__menu-item"
        role="menuitem"
        data-testid="fav-remove"
        @click="remove"
      >
        {{ t("actions.favoriteRemove") }}
      </Button>
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

.fav__main {
  position: relative;
}

/* The split button reads as one outlined pill: both segments share the outer
   radius, the inner edge is square and the divider is the toggle's border. */
.fav--detail .fav__main {
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
  border-right-width: 0;
}

.fav__toggle {
  width: var(--gv-size-control-lg);
  padding: 0;
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
}

.fav--card .fav__main {
  width: var(--gv-size-control-sm);
  padding: 0;
}

.fav--toolbar .fav__main {
  width: var(--gv-size-control-lg);
  padding: 0;
}

.fav__heart {
  color: var(--gv-color-on-surface-variant);
  transition: color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.fav__heart--active {
  filter: drop-shadow(0 0 var(--gv-space-xs) var(--gv-color-surface));
}

.fav__label {
  white-space: nowrap;
}

.fav__main:disabled .fav__heart {
  color: inherit;
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

.fav__menu {
  position: absolute;
  inset-inline-end: 0;
  top: calc(100% + var(--gv-space-1));
  z-index: 31;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 180px;
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.fav__menu-item {
  justify-content: flex-start;
  width: 100%;
}

/* --gv-bp-compact = 600px: the detail row must stay on one line above the
   mobile bottom bar, so the split button keeps both segments but drops the
   label (the aria-label still names it). */
@media (max-width: 599.98px) {
  .fav--detail .fav__main {
    width: var(--gv-size-control-lg);
    padding: 0;
  }

  .fav--detail .fav__label {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .fav__heart {
    transition-duration: 1ms;
  }

  .fav__spinner {
    animation-duration: 2s;
  }
}
</style>
