<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import { tagLabel, tagRawText, type TagLike } from "./tag-utils";
import { useTagNavigation, type TagSource } from "./useTagNavigation";
import "./i18n";

/**
 * Long-press / right-click menu for one tag. Desktop and touch share the same
 * items: copy the raw `ns:name`, filter the local library, search online and
 * exclude the tag. Blocking / subscribing are intentionally out of scope.
 */
const props = withDefaults(
  defineProps<{
    tag: TagLike;
    x: number;
    y: number;
    source?: TagSource;
  }>(),
  { source: "local" },
);

const emit = defineEmits<{
  close: [];
  copied: [text: string];
}>();

const { t, locale } = useI18n();
const local = useTagNavigation("local");
const online = useTagNavigation("online");

const label = computed(() => tagLabel(props.tag, locale.value));
const raw = computed(() => tagRawText(props.tag));

const position = computed(() => {
  const viewportWidth = typeof window === "undefined" ? 1280 : window.innerWidth;
  const viewportHeight = typeof window === "undefined" ? 900 : window.innerHeight;
  const left = Math.min(Math.max(8, props.x), Math.max(8, viewportWidth - 248));
  const top = Math.min(Math.max(8, props.y), Math.max(8, viewportHeight - 232));
  return { left: `${left}px`, top: `${top}px` };
});

function close(): void {
  emit("close");
}

function onDocumentPointer(event: Event): void {
  const target = event.target;
  if (target instanceof Element && target.closest(".tag-menu")) return;
  close();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") close();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer, true);
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer, true);
  document.removeEventListener("keydown", onKeydown);
});

function fallbackCopy(text: string): boolean {
  if (typeof document === "undefined") return false;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = typeof document.execCommand === "function" && document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(area);
  return ok;
}

async function copyRaw(): Promise<void> {
  const text = raw.value;
  let copied = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      copied = true;
    }
  } catch {
    copied = false;
  }
  if (!copied) copied = fallbackCopy(text);
  if (copied) emit("copied", text);
  close();
}

function filterLocal(): void {
  void local.navigate(props.tag);
  close();
}

function searchOnline(): void {
  void online.navigate(props.tag);
  close();
}

function excludeTag(): void {
  const target = props.source === "online" ? online : local;
  void target.navigate(props.tag, { exclude: true });
  close();
}
</script>

<template>
  <Teleport to="body">
    <div
      class="tag-menu"
      role="menu"
      data-testid="tag-menu"
      :style="position"
      @click.stop
      @contextmenu.prevent.stop
    >
      <div class="tag-menu__head">
        <span class="tag-menu__label">{{ label }}</span>
        <span class="tag-menu__raw">{{ raw }}</span>
      </div>
      <button
        type="button"
        role="menuitem"
        class="tag-menu__item"
        data-testid="tag-menu-copy"
        @click="copyRaw"
      >
        <Icon name="copy" size="dense" />
        <span>{{ t("tagsUi.menu.copy") }}</span>
      </button>
      <button
        type="button"
        role="menuitem"
        class="tag-menu__item"
        data-testid="tag-menu-filter"
        @click="filterLocal"
      >
        <Icon name="library" size="dense" />
        <span>{{ t("tagsUi.menu.filter") }}</span>
      </button>
      <button
        type="button"
        role="menuitem"
        class="tag-menu__item"
        data-testid="tag-menu-search"
        @click="searchOnline"
      >
        <Icon name="search" size="dense" />
        <span>{{ t("tagsUi.menu.search") }}</span>
      </button>
      <button
        type="button"
        role="menuitem"
        class="tag-menu__item tag-menu__item--danger"
        data-testid="tag-menu-exclude"
        @click="excludeTag"
      >
        <Icon name="status-blocked" size="dense" />
        <span>{{ t("tagsUi.menu.exclude") }}</span>
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.tag-menu {
  position: fixed;
  z-index: 80;
  display: flex;
  flex-direction: column;
  min-width: 220px;
  max-width: 288px;
  padding: var(--gv-space-1);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  color: var(--gv-color-on-surface);
  box-shadow: var(--gv-elev-3);
}

.tag-menu__head {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-0);
  padding: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.tag-menu__label {
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface);
  overflow-wrap: anywhere;
}

.tag-menu__raw {
  font: var(--gv-type-label-small);
  color: var(--gv-color-on-surface-variant);
  overflow-wrap: anywhere;
}

.tag-menu__item {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-control-md);
  padding: 0 var(--gv-space-2);
  border: 0;
  border-radius: var(--gv-radius-xs);
  background: transparent;
  color: inherit;
  font: var(--gv-type-body-medium);
  text-align: start;
  cursor: pointer;
}

.tag-menu__item:hover {
  background: var(--gv-color-surface-variant);
}

.tag-menu__item:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: calc(var(--gv-state-focus-ring-offset) * -1);
}

.tag-menu__item--danger {
  color: var(--gv-color-error);
}
</style>
