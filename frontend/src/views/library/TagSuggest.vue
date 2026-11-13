<script setup lang="ts">
/**
 * Tag-aware search field shared by browse and the local library.
 *
 * It is the shared `Input` control (one control-ladder step, no hand-written
 * field chrome) plus a suggestions popover. The popover is a listbox of
 * `Button`s, so keyboard / hover states come from the design system rather than
 * ad-hoc background rules.
 *
 * The inner input is owned by `Input`, which does not forward listeners to it;
 * key handling therefore sits on the wrapper and reads the bubbled keydown.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
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

function onValue(value: string): void {
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

function onFocusIn(event: FocusEvent): void {
  const target = event.target as HTMLElement | null;
  if (target?.tagName !== "INPUT") return;
  if (props.modelValue.trim()) schedule(props.modelValue);
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!open.value && props.modelValue.trim()) {
      schedule(props.modelValue);
      return;
    }
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
      return;
    }
    // `Input` prevents the native Enter submit; keep the form working here.
    const form = (event.target as HTMLElement | null)?.closest("form");
    if (form) {
      event.preventDefault();
      form.requestSubmit();
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
  <div
    ref="root"
    class="tag-suggest"
    role="combobox"
    :aria-expanded="open"
    :aria-controls="listId"
    aria-haspopup="listbox"
    :data-testid="testid"
    @focusin="onFocusIn"
    @keydown="onKeydown"
  >
    <Input
      :model-value="modelValue"
      class="tag-suggest__field"
      :placeholder="placeholder"
      :aria-label="label || placeholder || t('library.page.search')"
      autocomplete="off"
      @update:model-value="onValue"
    />
    <div v-if="open" :id="listId" class="tag-suggest__menu" role="listbox">
      <Button
        v-for="(tag, index) in suggestions"
        :key="`${tag.namespace ?? ''}:${tag.name}`"
        class="tag-suggest__item"
        :variant="index === activeIndex ? 'tonal' : 'text'"
        role="option"
        :aria-selected="index === activeIndex"
        data-testid="tag-suggestion"
        @mousedown.prevent="choose(tag)"
        @mouseenter="activeIndex = index"
      >
        <span class="tag-suggest__name">{{ tag.display || tag.name }}</span>
        <span class="tag-suggest__ns">{{ tag.namespace }} · {{ tag.usage_count }}</span>
      </Button>
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

.tag-suggest__field {
  width: 100%;
}

.tag-suggest__menu {
  position: absolute;
  top: calc(100% + var(--gv-space-1));
  right: 0;
  left: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 280px;
  padding: var(--gv-space-1);
  overflow-y: auto;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.tag-suggest__item {
  width: 100%;
  justify-content: space-between;
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
