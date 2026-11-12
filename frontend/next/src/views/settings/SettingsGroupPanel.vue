<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import SettingsRow from "./SettingsRow.vue";
import type { SettingAction, SettingField, SettingGroup } from "./schema";

const props = withDefaults(
  defineProps<{
    group: SettingGroup;
    values: Record<string, unknown>;
    customBaseUrl?: string;
    configured?: Record<string, boolean>;
    display?: Record<string, string>;
    disabled?: boolean;
  }>(),
  {
    customBaseUrl: "",
    configured: () => ({}),
    display: () => ({}),
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
const visibleActions = computed<SettingAction[]>(() =>
  props.group.actions.filter((action) => !CUSTOM_ACTION_KINDS.has(action.kind)),
);

function isLink(action: SettingAction): boolean {
  return action.kind === "link";
}

function actionHref(action: SettingAction): string {
  return action.to ? `#${action.to}` : "#/settings";
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
        :disabled="disabled"
        @update:value="emit('update', field.key, $event)"
        @update:custom-base-url="emit('update:customBaseUrl', $event)"
      />
    </div>

    <div v-if="visibleActions.length" class="group__actions" data-settings-actions>
      <h3 class="group__actions-title">{{ t('settings.actions') }}</h3>
      <div class="group__action-row">
        <template v-for="action in visibleActions" :key="action.id">
          <a
            v-if="isLink(action)"
            class="group__link"
            :href="actionHref(action)"
            :data-action-id="action.id"
          >
            {{ t(action.labelKey) }}
          </a>
          <Button
            v-else
            variant="outlined"
            size="compact"
            :disabled="disabled"
            :data-action-id="action.id"
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

.group__title {
  margin: 0;
  font: var(--gv-type-label-large);
  color: var(--gv-color-primary-text);
}

.group__description {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.group__fields {
  overflow: hidden;
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.group__fields :deep(.row:last-child) {
  border-bottom: none;
}

.group__actions {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-4);
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

.group__link {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-4);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.group__action-help {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}
</style>
