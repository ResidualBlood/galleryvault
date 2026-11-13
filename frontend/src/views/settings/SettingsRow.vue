<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import type { SettingField } from "./schema";

const props = withDefaults(
  defineProps<{
    field: SettingField;
    value: unknown;
    customBaseUrl?: string;
    configured?: boolean;
    display?: string;
    disabled?: boolean;
  }>(),
  {
    customBaseUrl: "",
    configured: false,
    display: "",
    disabled: false,
  },
);

const emit = defineEmits<{
  "update:value": [value: unknown];
  "update:customBaseUrl": [value: string];
}>();

const { t } = useI18n();

const label = computed(() => t(props.field.labelKey));
const help = computed(() => (props.field.helpKey ? t(props.field.helpKey) : ""));
const options = computed(() =>
  (props.field.options ?? []).map((option) => ({
    value: option.value,
    label: t(option.labelKey),
  })),
);

const textValue = computed(() => {
  const value = props.value;
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
});

const isCustomBaseUrl = computed(() => textValue.value === "__custom__");
const numericValue = computed(() => (props.value === undefined ? "" : String(props.value ?? "")));

const onlineDefaults = computed(() => {
  const value = (props.value ?? {}) as {
    list?: unknown;
    tl?: unknown;
    min_rating?: unknown;
  };
  return {
    list: String(value.list ?? "search"),
    tl: String(value.tl ?? 15),
    min_rating: value.min_rating === null || value.min_rating === undefined ? "" : String(value.min_rating),
  };
});

const onlineListOptions = computed(() => [
  { value: "search", label: t("settings.option.onlineList.search") },
  { value: "popular", label: t("settings.option.onlineList.popular") },
  { value: "watched", label: t("settings.option.onlineList.watched") },
  { value: "toplist", label: t("settings.option.onlineList.toplist") },
]);

const toplistOptions = ["11", "12", "13", "15"].map((value) => ({
  value,
  label: t(`settings.option.toplist.${value}`),
}));

const ratingOptions = computed(() => [
  { value: "", label: t("settings.option.rating.any") },
  ...[2, 3, 4, 5].map((value) => ({
    value: String(value),
    label: t("settings.option.rating.atLeast", { value }),
  })),
]);

function updateOnline(patch: Record<string, unknown>): void {
  emit("update:value", { ...onlineDefaults.value, ...patch });
}

function update(value: unknown): void {
  emit("update:value", value);
}

const readonlyText = computed(() => {
  if (props.display) return props.display;
  const value = props.value;
  if (typeof value === "boolean") {
    return value ? t("settings.yes") : t("settings.no");
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((entry) => String(entry)).join(", ") : t("settings.none");
  }
  if (value === null || value === undefined || value === "") {
    return props.field.storage === "env" ? t("settings.envManaged") : "—";
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
});
</script>

<template>
  <div class="row" :data-setting-key="field.key" :data-setting-control="field.control">
    <div class="row__text">
      <div class="row__title-line">
        <span class="row__title">{{ label }}</span>
        <span v-if="field.security" class="row__badge">{{ t("settings.securityBadge") }}</span>
      </div>
      <p v-if="help" class="row__help">{{ help }}</p>
      <p v-if="field.secret && configured" class="row__state">{{ t("settings.configured") }}</p>
    </div>

    <div class="row__control">
      <Switch
        v-if="field.control === 'switch'"
        :model-value="Boolean(value)"
        :label="label"
        :disabled="disabled"
        @update:model-value="update"
      />

      <Select
        v-else-if="field.control === 'select'"
        :model-value="textValue"
        :options="options"
        :disabled="disabled"
        @update:model-value="update"
      />

      <template v-else-if="field.control === 'baseurl'">
        <Select
          :model-value="textValue"
          :options="options"
          :disabled="disabled"
          @update:model-value="update"
        />
        <Input
          v-if="isCustomBaseUrl"
          class="row__custom"
          :model-value="customBaseUrl"
          :placeholder="t('settings.customBaseUrl')"
          :disabled="disabled"
          @update:model-value="emit('update:customBaseUrl', $event)"
        />
      </template>

      <Input
        v-else-if="field.control === 'number'"
        :model-value="numericValue"
        type="number"
        :disabled="disabled"
        :autocomplete="'off'"
        @update:model-value="update"
      />

      <Input
        v-else-if="field.control === 'secret'"
        :model-value="textValue"
        type="password"
        autocomplete="new-password"
        :placeholder="t('settings.secretPlaceholder')"
        :disabled="disabled"
        data-secret-input="true"
        @update:model-value="update"
      />

      <Input
        v-else-if="field.control === 'text'"
        :model-value="textValue"
        type="text"
        :disabled="disabled"
        @update:model-value="update"
      />

      <textarea
        v-else-if="field.control === 'textarea'"
        class="row__textarea"
        :value="textValue"
        :disabled="disabled"
        rows="3"
        :aria-label="label"
        @input="update(($event.target as HTMLTextAreaElement).value)"
      />

      <div v-else-if="field.control === 'online-defaults'" class="row__stack">
        <Select
          :model-value="onlineDefaults.list"
          :options="onlineListOptions"
          @update:model-value="updateOnline({ list: $event })"
        />
        <Select
          v-if="onlineDefaults.list === 'toplist'"
          :model-value="onlineDefaults.tl"
          :options="toplistOptions"
          @update:model-value="updateOnline({ tl: $event })"
        />
        <Select
          :model-value="onlineDefaults.min_rating"
          :options="ratingOptions"
          @update:model-value="updateOnline({ min_rating: $event === '' ? null : $event })"
        />
      </div>

      <a
        v-else-if="field.control === 'link'"
        class="row__link"
        :href="field.href"
        :download="field.download ? '' : undefined"
        :target="field.external ? '_blank' : undefined"
        :rel="field.external ? 'noreferrer noopener' : undefined"
      >
        {{ label }}
      </a>

      <span v-else class="row__readonly" data-readonly-value>{{ readonlyText }}</span>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--gv-space-4);
  min-height: var(--gv-size-topbar);
  padding: var(--gv-space-3) var(--gv-space-4);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.row__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.row__title-line {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  flex-wrap: wrap;
}

.row__title {
  font: var(--gv-type-body-large);
  color: var(--gv-color-on-surface);
}

.row__badge {
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
  font: var(--gv-type-label-small);
}

.row__help {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.row__state {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-success);
}

.row__control {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: var(--gv-space-2);
  align-items: flex-end;
  min-width: 220px;
  max-width: 320px;
}

.row__stack {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  width: 100%;
}

.row__custom,
.row__textarea {
  width: 100%;
}

.row__textarea {
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  resize: vertical;
}

.row__textarea:focus {
  outline: none;
  border-color: var(--gv-color-primary);
  box-shadow: 0 0 0 1px var(--gv-color-primary);
}

.row__readonly {
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
  text-align: right;
  overflow-wrap: anywhere;
}

.row__link {
  font: var(--gv-type-label-large);
  color: var(--gv-color-primary-text);
}

@media (max-width: 839px) {
  .row {
    flex-direction: column;
    gap: var(--gv-space-2);
  }

  .row__control {
    width: 100%;
    max-width: none;
    min-width: 0;
    align-items: stretch;
  }
}
</style>
