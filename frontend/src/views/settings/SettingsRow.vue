<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Switch from "@/components/ui/Switch.vue";
import TextArea from "@/components/ui/TextArea.vue";
import type { SettingField } from "./schema";
import type { SettingTone } from "./types";

const props = withDefaults(
  defineProps<{
    field: SettingField;
    value: unknown;
    customBaseUrl?: string;
    configured?: boolean;
    display?: string;
    tone?: SettingTone;
    disabled?: boolean;
  }>(),
  {
    customBaseUrl: "",
    configured: false,
    display: "",
    tone: "neutral",
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

/** Unit suffixes live on the control, never inside the row title (ST02-03/06-02/09-03). */
const UNITS: Record<string, string> = {
  gv_page_size: "settings.unit.items",
  gv_slideshow_interval: "settings.unit.seconds",
  online_reader_concurrency: "settings.unit.galleries",
  online_cache_max_mb: "settings.unit.megabytes",
  download_concurrency: "settings.unit.galleries",
  page_concurrency: "settings.unit.images",
  image_download_timeout_seconds: "settings.unit.seconds",
  image_slow_warmup_seconds: "settings.unit.seconds",
  image_min_speed_kb_s: "settings.unit.kbPerSecond",
  favorites_archive_max_pages: "settings.unit.pages",
  tag_sync_interval_seconds: "settings.unit.seconds",
  tag_sync_concurrency: "settings.unit.galleries",
  tag_translation_update_interval_minutes: "settings.unit.minutes",
};

const unit = computed(() => {
  const key = UNITS[props.field.key];
  return key ? t(key) : "";
});

/** Machine-facing keys are helpers, never row titles (ST03-01). */
const INTERNAL_KEY_FIELDS = new Set([
  "ipb_member_id",
  "ipb_pass_hash",
  "igneous",
  "exhentai_cookie_configured",
  "exhentai_cookie_names",
  "exhentai_max_concurrency",
  "download_max_retries",
  "cold_storage_root",
  "telegram_bot_configured",
  "auth_hash_configured",
  "integration_opds_url",
  "thumbnail_cache_dir",
]);
const showInternalKey = computed(() => INTERNAL_KEY_FIELDS.has(props.field.key));

/** Example formats for ID / proxy fields (ST10-03). */
const PLACEHOLDERS: Record<string, string> = {
  telegram_chat_ids: "-100123456789",
  telegram_allowed_user_ids: "123456789",
  http_proxy: "http://127.0.0.1:8080",
  socks5_proxy: "socks5://127.0.0.1:1080",
};
const placeholder = computed(() => PLACEHOLDERS[props.field.key] ?? "");

/** Machine IDs and proxy URLs read better in a monospace face. */
const MONO_FIELDS = new Set([
  "telegram_chat_ids",
  "telegram_allowed_user_ids",
  "http_proxy",
  "socks5_proxy",
]);
const mono = computed(() => MONO_FIELDS.has(props.field.key));

const destructive = computed(() => props.field.key === "archive_delete_source");

const multiline = computed(
  () => props.field.control === "textarea" || props.field.control === "online-defaults",
);

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
    return props.field.storage === "env" ? t("settings.envManaged") : t("settings.none");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
});

/** Paths / URLs get a monospace, copyable, left-aligned value (ST12-02, ST13-04). */
const pathValue = computed(
  () =>
    props.field.key === "integration_opds_url" ||
    props.field.key === "thumbnail_cache_dir" ||
    props.field.key === "cold_storage_root",
);

const toneIcon = computed(() => {
  if (props.tone === "success") return "status-success" as const;
  if (props.tone === "warning") return "status-warning" as const;
  if (props.tone === "error") return "status-error" as const;
  return null;
});

const linkLabel = computed(() => {
  const key = `settings.link.${props.field.key}`;
  const text = t(key);
  return text === key ? label.value : text;
});

const copyState = ref<"idle" | "copied" | "failed">("idle");
let copyTimer: number | null = null;
async function copyValue(): Promise<void> {
  try {
    await navigator.clipboard.writeText(readonlyText.value);
    copyState.value = "copied";
  } catch {
    copyState.value = "failed";
  }
  if (copyTimer !== null) window.clearTimeout(copyTimer);
  copyTimer = window.setTimeout(() => {
    copyState.value = "idle";
  }, 1600);
}

const copyLabel = computed(() => {
  if (copyState.value === "copied") return t("settings.copied");
  if (copyState.value === "failed") return t("settings.copyFailed");
  return t("settings.copy");
});
</script>

<template>
  <div
    class="row"
    :class="{ 'row--multiline': multiline, 'row--destructive': destructive }"
    :data-setting-key="field.key"
    :data-setting-control="field.control"
  >
    <div class="row__text">
      <div class="row__title-line">
        <span class="row__title">{{ label }}</span>
        <span v-if="field.security" class="row__badge">
          <Icon name="status-auth" size="sm" aria-hidden="true" />
          {{ t("settings.securityBadge") }}
        </span>
      </div>
      <p v-if="help" class="row__help">
        <Icon
          v-if="destructive"
          name="status-warning"
          size="sm"
          class="row__help-icon"
          aria-hidden="true"
        />
        {{ help }}
      </p>
      <p v-if="showInternalKey" class="row__key">
        {{ t("settings.internalKey") }} <code>{{ field.key }}</code>
      </p>
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
          :model-value="customBaseUrl"
          :placeholder="t('settings.customBaseUrl')"
          :disabled="disabled"
          @update:model-value="emit('update:customBaseUrl', $event)"
        />
      </template>

      <Input
        v-else-if="field.control === 'number'"
        class="row__number"
        :model-value="numericValue"
        type="number"
        :unit="unit"
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
        class="row__text-input"
        :class="{ 'row__text-input--mono': mono }"
        :model-value="textValue"
        type="text"
        :placeholder="placeholder"
        :disabled="disabled"
        @update:model-value="update"
      />

      <TextArea
        v-else-if="field.control === 'textarea'"
        :model-value="textValue"
        :aria-label="label"
        :rows="3"
        :disabled="disabled"
        @update:model-value="update"
      />

      <div v-else-if="field.control === 'online-defaults'" class="row__stack">
        <Select
          :model-value="onlineDefaults.list"
          :label="t('settings.onlineDefaults.list')"
          :options="onlineListOptions"
          @update:model-value="updateOnline({ list: $event })"
        />
        <Select
          v-if="onlineDefaults.list === 'toplist'"
          :model-value="onlineDefaults.tl"
          :label="t('settings.onlineDefaults.tl')"
          :options="toplistOptions"
          @update:model-value="updateOnline({ tl: $event })"
        />
        <Select
          :model-value="onlineDefaults.min_rating"
          :label="t('settings.onlineDefaults.minRating')"
          :options="ratingOptions"
          @update:model-value="updateOnline({ min_rating: $event === '' ? null : $event })"
        />
      </div>

      <a
        v-else-if="field.control === 'link'"
        class="row__value row__value--link"
        :href="field.href"
        :download="field.download ? '' : undefined"
        :target="field.external ? '_blank' : undefined"
        :rel="field.external ? 'noreferrer noopener' : undefined"
      >
        <Icon :name="field.external ? 'external-link' : 'downloads'" size="sm" aria-hidden="true" />
        <span>{{ linkLabel }}</span>
      </a>

      <div v-else-if="pathValue" class="row__value row__value--path">
        <code class="row__code" :title="readonlyText">{{ readonlyText }}</code>
        <IconButton
          name="copy"
          size="sm"
          :label="copyLabel"
          @click="copyValue"
        />
      </div>

      <span v-else class="row__value" :data-tone="tone" data-readonly-value>
        <Icon v-if="toneIcon" :name="toneIcon" size="sm" aria-hidden="true" />
        <span class="row__value-text">{{ readonlyText }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.row {
  --row-control-width: 280px;

  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--row-control-width);
  align-items: start;
  gap: var(--gv-space-4);
  min-height: calc(var(--gv-space-8) + var(--gv-space-2));
  padding: var(--gv-space-4);
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

/* Centre the title's first line on the control's centre line (ST01-03/02-02/03-05). */
.row__text {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
  padding-top: calc((var(--gv-size-control-lg) - var(--gv-type-body-large-line)) / 2);
}

.row--multiline .row__text {
  padding-top: 0;
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
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: calc(var(--gv-space-4) + var(--gv-space-1));
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-tertiary-container);
  color: var(--gv-color-on-tertiary-container);
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.row__help {
  display: flex;
  align-items: flex-start;
  gap: var(--gv-space-1);
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.row--destructive .row__help {
  color: var(--gv-color-warning);
}

.row__help-icon {
  flex: none;
  margin-top: calc(var(--gv-space-1) / 2);
  color: var(--gv-color-warning);
}

.row__key {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.row__key code,
.row__code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  font-size: var(--gv-type-body-small-size);
}

.row__state {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-success);
}

.row__control {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--gv-space-2);
  width: 100%;
  min-width: 0;
  min-height: var(--gv-size-control-lg);
}

.row__control :deep(.switch) {
  align-self: flex-end;
}

.row__stack {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  width: 100%;
}

.row__text-input--mono :deep(.field__control) {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  font-size: var(--gv-type-body-medium-size);
}

.row__number :deep(.field__control) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.row__number :deep(.field__unit) {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.row__value {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--gv-space-2);
  width: 100%;
  min-height: var(--gv-size-control-lg);
  padding: 0 var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-lowest);
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
}

.row__value[data-tone="success"] {
  border-color: var(--gv-color-success-container);
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
}

.row__value[data-tone="warning"] {
  border-color: var(--gv-color-warning-container);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
}

.row__value[data-tone="error"] {
  border-color: var(--gv-color-error-container);
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.row__value-text {
  overflow-wrap: anywhere;
  text-align: right;
}

.row__value--path {
  justify-content: flex-start;
  padding-right: var(--gv-space-1);
}

.row__code {
  flex: 1;
  min-width: 0;
  color: var(--gv-color-on-surface-variant);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row__value--link {
  justify-content: flex-start;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.row__value--link:hover {
  background: var(--gv-color-surface-container-high);
}

@media (max-width: 839px) {
  .row {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--gv-space-2);
  }

  .row__text {
    padding-top: 0;
  }

  .row__control {
    width: 100%;
  }

  .row__value {
    justify-content: flex-start;
  }

  .row__value-text {
    text-align: left;
  }
}
</style>
