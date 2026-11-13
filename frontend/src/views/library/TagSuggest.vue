<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { fetchTagSuggestions, type TagSuggestion } from "@/api/library";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    label?: string;
    placeholder?: string;
    testid?: string;
  }>(),
  {
    label: "",
    placeholder: "",
    testid: "tag-suggest",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  select: [tag: TagSuggestion];
}>();

const { t } = useI18n();
const root = ref<HTMLElement | null>(null);
const suggestions = ref<TagSuggestion[]>([]);
const open = ref(false);
const loading = ref(false);
const activeIndex = ref(-1);
let timer: ReturnType<typeof setTimeout> | null = null;
let controller: AbortController | null = null;
const listId = `gv-tag-suggest-${Math.random().toString(36).slice(2, 8)}`;

const showEmpty = computed(
  () => open.value && !loading.value && suggestions.value.length === 0,
);

async function search(term: string): Promise<void> {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  try {
    const data = await fetchTagSuggestions(term, controller.signal);
    suggestions.value = data.items ?? [];
    activeIndex.value = suggestions.value.length ? 0 : -1;
    open.value = true;
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") return;
    suggestions.value = [];
    open.value = true;
  } finally {
    loading.value = false;
  }
}

function schedule(term: string): void {
  if (timer) clearTimeout(timer);
  const trimmed = term.trim();
  if (!trimmed) {
    controller?.abort();
    suggestions.value = [];
    open.value = false;
    return;
  }
  timer = setTimeout(() => void search(trimmed), 200);
}

function onInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  emit("update:modelValue", value);
  schedule(value);
}

function choose(tag: TagSuggestion): void {
  emit("select", tag);
  open.value = false;
  suggestions.value = [];
}

function move(delta: number): void {
  if (!suggestions.value.length) return;
  activeIndex.value =
    (activeIndex.value + delta + suggestions.value.length) % suggestions.value.length;
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    move(1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    move(-1);
    return;
  }
  if (event.key === "Escape") {
    open.value = false;
    return;
  }
  if (event.key === "Enter") {
    if (open.value && activeIndex.value >= 0 && suggestions.value[activeIndex.value]) {
      event.preventDefault();
      choose(suggestions.value[activeIndex.value]);
    }
  }
}

function onDocumentPointer(event: Event): void {
  if (!root.value?.contains(event.target as Node)) open.value = false;
}

watch(
  () => props.modelValue,
  (value) => {
    if (!value.trim()) {
      open.value = false;
      suggestions.value = [];
    }
  },
);

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer);
});

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
  controller?.abort();
  document.removeEventListener("pointerdown", onDocumentPointer);
});
</script>

<template>
  <div ref="root" class="tag-suggest" :data-testid="testid">
    <input
      class="tag-suggest__input"
      type="search"
      role="combobox"
      :value="modelValue"
      :placeholder="placeholder"
      :aria-label="label || placeholder"
      :aria-expanded="open"
      :aria-controls="listId"
      aria-autocomplete="list"
      autocomplete="off"
      @input="onInput"
      @focus="modelValue.trim() && schedule(modelValue)"
      @keydown="onKeydown"
    />
    <div v-if="open" :id="listId" class="tag-suggest__menu" role="listbox">
      <button
        v-for="(tag, index) in suggestions"
        :key="`${tag.namespace ?? ''}:${tag.name}`"
        type="button"
        role="option"
        class="tag-suggest__item"
        :class="{ 'tag-suggest__item--active': index === activeIndex }"
        :aria-selected="index === activeIndex"
        data-testid="tag-suggestion"
        @mousedown.prevent="choose(tag)"
        @mouseenter="activeIndex = index"
      >
        <span class="tag-suggest__name">{{ tag.display || tag.name }}</span>
        <span class="tag-suggest__ns">{{ tag.namespace }} · {{ tag.usage_count }}</span>
      </button>
      <p v-if="showEmpty" class="tag-suggest__empty">
        {{ t("library.page.tagSuggestEmpty") }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.tag-suggest {
  position: relative;
  flex: 1;
  min-width: 180px;
}

.tag-suggest__input {
  width: 100%;
  height: 48px;
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-large);
}

.tag-suggest__input::placeholder {
  color: var(--gv-color-on-surface-variant);
}

.tag-suggest__input:focus {
  outline: none;
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 1px var(--gv-color-primary);
}

.tag-suggest__menu {
  position: absolute;
  top: calc(100% + var(--gv-space-1));
  right: 0;
  left: 0;
  z-index: 20;
  max-height: 280px;
  padding: var(--gv-space-1);
  overflow-y: auto;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.tag-suggest__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 40px;
  padding: 0 var(--gv-space-2);
  border: 0;
  border-radius: var(--gv-radius-xs);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  text-align: start;
  cursor: pointer;
}

.tag-suggest__item--active,
.tag-suggest__item:hover {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.tag-suggest__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-suggest__ns {
  flex: none;
  margin-left: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.tag-suggest__empty {
  margin: 0;
  padding: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
