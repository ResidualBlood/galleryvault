<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import { ensureLayoutMessages } from "./i18n/layout";

ensureLayoutMessages();

const props = withDefaults(
  defineProps<{
    page: number;
    /** Omit (or pass 0) when the backend has no total count. */
    totalPages?: number;
    pageSize?: number;
    pageSizeOptions?: number[];
    disabled?: boolean;
    showJump?: boolean;
    testid?: string;
  }>(),
  {
    totalPages: 0,
    pageSize: undefined,
    pageSizeOptions: () => [],
    disabled: false,
    showJump: true,
    testid: "gv-pager",
  },
);

const emit = defineEmits<{
  "update:page": [page: number];
  "update:pageSize": [size: number];
}>();

const { t } = useI18n();

const total = computed(() => (props.totalPages && props.totalPages > 0 ? props.totalPages : 0));
const hasTotal = computed(() => total.value > 0);
const jumpDraft = ref(String(props.page));
const jumpError = ref("");

watch(
  () => props.page,
  (value) => {
    jumpDraft.value = String(value);
    jumpError.value = "";
  },
);

const pages = computed<Array<number | "gap">>(() => {
  const count = total.value;
  if (!count) return [];
  if (count <= 7) return Array.from({ length: count }, (_, index) => index + 1);
  const start = Math.max(2, Math.min(props.page - 1, count - 4));
  const end = Math.min(count - 1, start + 3);
  const output: Array<number | "gap"> = [1];
  if (start > 2) output.push("gap");
  for (let page = start; page <= end; page += 1) output.push(page);
  if (end < count - 1) output.push("gap");
  output.push(count);
  return output;
});

const canPrev = computed(() => !props.disabled && props.page > 1);
const canNext = computed(
  () => !props.disabled && (!hasTotal.value || props.page < total.value),
);

function go(page: number): void {
  if (props.disabled) return;
  const next = hasTotal.value ? Math.min(Math.max(page, 1), total.value) : page;
  if (next !== props.page) emit("update:page", next);
}

function submitJump(): void {
  const value = Number(jumpDraft.value.trim());
  if (!Number.isInteger(value) || value < 1 || value > total.value) {
    jumpError.value = t("kit.pager.jumpInvalid", { total: total.value });
    jumpDraft.value = String(props.page);
    return;
  }
  jumpError.value = "";
  go(value);
}

function onPageSize(event: Event): void {
  emit("update:pageSize", Number((event.target as HTMLSelectElement).value));
}
</script>

<template>
  <nav
    class="pager"
    :aria-label="t('kit.pager.label')"
    :data-testid="testid"
  >
    <button
      class="pager__button"
      type="button"
      :aria-label="t('kit.pager.previous')"
      data-pager="prev"
      :disabled="!canPrev"
      @click="go(page - 1)"
    >
      <Icon name="chevron-left" size="dense" />
    </button>

    <ol v-if="hasTotal" class="pager__pages">
      <li v-for="(entry, index) in pages" :key="`${entry}-${index}`">
        <span v-if="entry === 'gap'" class="pager__gap" aria-hidden="true">…</span>
        <button
          v-else
          class="pager__page"
          :class="{ 'pager__page--current': entry === page }"
          type="button"
          :aria-label="t('kit.pager.pageNumber', { page: entry })"
          :aria-current="entry === page ? 'page' : undefined"
          :disabled="disabled"
          @click="go(entry)"
        >
          {{ entry }}
        </button>
      </li>
    </ol>

    <button
      class="pager__button"
      type="button"
      :aria-label="t('kit.pager.next')"
      data-pager="next"
      :disabled="!canNext"
      @click="go(page + 1)"
    >
      <Icon name="chevron-right" size="dense" />
    </button>

    <form v-if="hasTotal && showJump" class="pager__jump" @submit.prevent="submitJump">
      <label class="pager__jump-label" :for="`${testid}-jump`">
        {{ t("kit.pager.jumpLabel") }}
      </label>
      <input
        :id="`${testid}-jump`"
        v-model="jumpDraft"
        class="pager__input"
        :class="{ 'pager__input--invalid': Boolean(jumpError) }"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :placeholder="t('kit.pager.jumpPlaceholder')"
        :aria-label="t('kit.pager.jumpLabel')"
        :aria-invalid="Boolean(jumpError) || undefined"
        :aria-describedby="jumpError ? `${testid}-jump-error` : undefined"
        :disabled="disabled"
        data-pager="jump"
        @blur="submitJump"
      />
      <span v-if="jumpError" :id="`${testid}-jump-error`" class="pager__error" role="alert">
        {{ jumpError }}
      </span>
    </form>

    <label v-if="hasTotal && pageSizeOptions.length" class="pager__size">
      <span class="pager__jump-label">{{ t("kit.pager.pageSize") }}</span>
      <select
        class="pager__select"
        :value="pageSize"
        :aria-label="t('kit.pager.pageSize')"
        :disabled="disabled"
        @change="onPageSize"
      >
        <option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
      </select>
    </label>

    <div v-if="$slots['date-jump']" class="pager__date">
      <slot name="date-jump" />
    </div>
  </nav>
</template>

<style scoped>
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface-variant);
}

.pager__button,
.pager__page {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--gv-size-control-md);
  min-width: var(--gv-size-control-md);
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.pager__button:hover:not(:disabled),
.pager__page:hover:not(:disabled) {
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.pager__button:focus-visible,
.pager__page:focus-visible,
.pager__input:focus-visible,
.pager__select:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.pager__button:disabled,
.pager__page:disabled,
.pager__input:disabled,
.pager__select:disabled {
  opacity: var(--gv-state-disabled);
  cursor: not-allowed;
}

.pager__pages {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.pager__page--current {
  border-color: transparent;
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.pager__gap {
  padding: 0 var(--gv-space-1);
}

.pager__jump,
.pager__size {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
}

.pager__jump-label {
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.pager__input {
  width: 72px;
  height: var(--gv-size-control-md);
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  text-align: center;
}

.pager__input--invalid {
  border-color: var(--gv-color-error);
}

.pager__error {
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.pager__select {
  height: var(--gv-size-control-md);
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}
</style>
