<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import SettingsRow from "./SettingsRow.vue";
import type { SettingAction, SettingField, SettingGroup } from "./schema";
import type { SettingTone } from "./types";

const props = withDefaults(
  defineProps<{
    group: SettingGroup;
    values: Record<string, unknown>;
    customBaseUrl?: string;
    configured?: Record<string, boolean>;
    display?: Record<string, string>;
    derived?: Record<string, string>;
    tones?: Record<string, SettingTone>;
    disabled?: boolean;
  }>(),
  {
    customBaseUrl: "",
    configured: () => ({}),
    display: () => ({}),
    derived: () => ({}),
    tones: () => ({}),
    disabled: false,
  },
);

const emit = defineEmits<{
  update: [key: string, value: unknown];
  "update:customBaseUrl": [value: string];
  action: [id: string];
}>();

const { t } = useI18n();

const CUSTOM_ACTION_KINDS = new Set(["change-password", "api-token"]);
/** One filled action per group; everything else is outlined or text. */
const PRIMARY_ACTION_IDS = new Set(["gen-thumbs", "sync-all-tags"]);
const DANGER_ACTION_IDS = new Set(["purge-sources", "logout"]);

const visibleActions = computed<SettingAction[]>(() =>
  props.group.actions.filter((action) => !CUSTOM_ACTION_KINDS.has(action.kind)),
);

function isLink(action: SettingAction): boolean {
  return action.kind === "link";
}

function actionHref(action: SettingAction): string {
  return action.to ?? "/settings";
}

function actionVariant(action: SettingAction): "filled" | "outlined" | "text" {
  if (isLink(action)) return "text";
  return PRIMARY_ACTION_IDS.has(action.id) ? "filled" : "outlined";
}

function fieldValue(field: SettingField): unknown {
  return props.values[field.key];
}
</script>

<template>
  <section class="group" :data-settings-group="group.id">
    <header class="group__header">
      <h2 class="group__title">{{ t(group.titleKey) }}</h2>
      <p class="group__description">{{ t(group.descriptionKey) }}</p>
    </header>

    <div class="group__fields">
      <SettingsRow
        v-for="field in group.fields"
        :key="field.key"
        :field="field"
        :value="fieldValue(field)"
        :custom-base-url="customBaseUrl"
        :configured="Boolean(configured[field.key])"
        :display="display[field.key] ?? ''"
        :derived="derived[field.key] ?? ''"
        :tone="tones[field.key] ?? 'neutral'"
        :disabled="disabled"
        @update:value="emit('update', field.key, $event)"
        @update:custom-base-url="emit('update:customBaseUrl', $event)"
      />
      <p class="group__footnote">{{ t('settings.groupHint') }}</p>
    </div>

    <div v-if="visibleActions.length" class="group__actions" data-settings-actions>
      <h3 class="group__actions-title">{{ t('settings.actions') }}</h3>
      <div class="group__action-row">
        <template v-for="action in visibleActions" :key="action.id">
          <a
            v-if="isLink(action)"
            class="group__link"
            :href="`#${actionHref(action)}`"
            :data-action-id="action.id"
          >
            <Icon name="chevron-right" size="sm" aria-hidden="true" />
            {{ t(action.labelKey) }}
          </a>
          <Button
            v-else
            :variant="actionVariant(action)"
            size="md"
            :danger="DANGER_ACTION_IDS.has(action.id)"
            :disabled="disabled"
            :data-action-id="action.id"
            :icon="action.kind === 'logout' ? 'logout' : undefined"
            @click="emit('action', action.id)"
          >
            {{ t(action.labelKey) }}
          </Button>
        </template>
      </div>
      <p v-for="action in visibleActions.filter((entry) => entry.helpKey)" :key="`${action.id}-help`" class="group__action-help">
        {{ t(action.helpKey ?? "") }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.group__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

/* Group title outranks the 16px row titles by weight and colour (ST00-03, ST11-04). */
.group__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.group__description {
  margin: 0;
  overflow: hidden;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group__fields {
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.group__fields :deep(.row:last-of-type) {
  border-bottom: none;
}

.group__footnote {
  margin: 0;
  padding: var(--gv-space-3) var(--gv-space-4);
  border-top: 1px solid var(--gv-color-outline-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.group__actions {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-low);
}

.group__actions-title {
  margin: 0;
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface-variant);
}

.group__action-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  align-items: center;
}

/* Links keep the md control height so the action row reads as one tier (ST05-01/08-01/09-01/13-01). */
.group__link {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  height: var(--gv-size-control-md);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.group__link:hover {
  background: var(--gv-color-surface-container-high);
}

.group__action-help {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

@media (max-width: 839px) {
  /* Stacked layout has no baseline to share, so descriptions may wrap. */
  .group__description {
    overflow: visible;
    white-space: normal;
  }
}
</style>
