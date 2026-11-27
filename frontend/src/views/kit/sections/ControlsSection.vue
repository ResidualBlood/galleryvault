<script setup lang="ts">
import { computed, defineComponent, ref, type PropType } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import Field from "@/components/ui/Field.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Slider from "@/components/ui/Slider.vue";
import Switch from "@/components/ui/Switch.vue";
import TextArea from "@/components/ui/TextArea.vue";
import {
  provideControlSize,
  type ControlSize,
} from "@/components/ui/control-size";
import { ensureControlMessages } from "@/components/ui/i18n/controls";

ensureControlMessages();

const { t } = useI18n();
const route = useRoute();

type ForcedState = "default" | "disabled" | "error" | "loading";

const forcedState = computed<ForcedState>(() => {
  const raw = Array.isArray(route.query.state) ? route.query.state[0] : route.query.state;
  if (raw === "disabled" || raw === "error" || raw === "loading") return raw;
  return "default";
});
const isDisabled = computed(() => forcedState.value === "disabled");
const isError = computed(() => forcedState.value === "error");
const isLoading = computed(() => forcedState.value === "loading");
const showMatrix = computed(() => forcedState.value !== "error");

const steps: Array<{ size: ControlSize; height: number }> = [
  { size: "lg", height: 40 },
  { size: "md", height: 36 },
  { size: "sm", height: 32 },
];

const sortOptions = computed(() => [
  { value: "id_desc", label: t("ui.controls.sort.newest") },
  { value: "id_asc", label: t("ui.controls.sort.oldest") },
]);

/**
 * Local scope used only by this specimen page: a Toolbar will provide the same
 * key later. It proves that a control without an explicit `size` inherits the
 * surrounding step.
 */
const ControlScope = defineComponent({
  name: "ControlScope",
  props: {
    size: { type: String as PropType<ControlSize>, required: true },
  },
  setup(props, { slots }) {
    provideControlSize(computed(() => props.size));
    return () => slots.default?.();
  },
});

const query = ref("nekopara");
const sort = ref("id_desc");
const switchOn = ref(true);
const checked = ref(true);
const mixed = ref(false);
const note = ref("");
const page = ref(12);
</script>

<template>
  <section class="controls" data-testid="kit-controls" aria-labelledby="kit-controls-title">
    <header class="controls__header">
      <h2 id="kit-controls-title" class="controls__title" data-testid="kit-focus-start" tabindex="-1">
        {{ t("ui.controls.section.title") }}
      </h2>
      <p class="controls__lede">{{ t("ui.controls.section.lede") }}</p>
    </header>

    <div v-if="showMatrix" class="controls__block">
      <h3 class="controls__subtitle">{{ t("ui.controls.alignment") }}</h3>
      <div class="controls__matrix">
        <div
          v-for="step in steps"
          :key="step.size"
          class="controls__row"
          data-gv-toolbar
          :data-testid="`kit-row-${step.size}`"
          :data-step="step.size"
          :data-height="step.height"
        >
          <span class="controls__row-label">{{ t(`ui.controls.size.${step.size}`) }}</span>
          <ControlScope :size="step.size">
            <Button
              icon="search"
              :disabled="isDisabled"
              :loading="isLoading"
              :data-testid="step.size === 'lg' ? 'kit-button-with-icon' : undefined"
            >
              {{ t("ui.controls.sample.button") }}
            </Button>
            <IconButton
              name="search"
              :label="t('ui.controls.sample.icon')"
              :disabled="isDisabled"
            />
            <Input
              v-model="query"
              icon="search"
              clearable
              :clear-label="t('ui.controls.clear')"
              :aria-label="t('ui.controls.sample.field')"
              :placeholder="t('ui.controls.sample.field')"
              :disabled="isDisabled"
            />
            <Select
              v-model="sort"
              :options="sortOptions"
              :aria-label="t('ui.controls.sample.select')"
              :disabled="isDisabled"
            />
          </ControlScope>
        </div>
      </div>
    </div>

    <div class="controls__block">
      <h3 class="controls__subtitle">{{ t("ui.controls.override") }}</h3>
      <div class="controls__row controls__row--plain">
        <ControlScope size="md">
          <Button size="lg">{{ t("ui.controls.size.lg") }}</Button>
          <Button size="sm">{{ t("ui.controls.size.sm") }}</Button>
        </ControlScope>
      </div>
    </div>

    <div class="controls__block">
      <h3 class="controls__subtitle">{{ t("ui.controls.states") }}</h3>
      <div class="controls__row controls__row--wrap controls__row--top">
        <Button
          data-testid="kit-disabled-filled"
          :disabled="true"
        >
          {{ t("ui.controls.disabled") }}
        </Button>
        <Button variant="tonal" :disabled="true">{{ t("ui.controls.disabled") }}</Button>
        <Button variant="outlined" :disabled="true">{{ t("ui.controls.disabled") }}</Button>
        <Button variant="text" :disabled="true">{{ t("ui.controls.disabled") }}</Button>
        <Button variant="outlined" danger>{{ t("ui.controls.error") }}</Button>
        <Button :loading="true">{{ t("ui.controls.loading") }}</Button>
        <IconButton
          name="search"
          :label="t('ui.controls.sample.icon')"
          :disabled="true"
        />
        <Input
          v-model="query"
          icon="search"
          :aria-label="t('ui.controls.sample.field')"
          :disabled="true"
        />
        <Select
          v-model="sort"
          :options="sortOptions"
          :aria-label="t('ui.controls.sample.select')"
          :disabled="true"
        />
      </div>
    </div>

    <div v-if="isError || forcedState === 'default'" class="controls__block">
      <h3 class="controls__subtitle">{{ t("ui.controls.error") }}</h3>
      <div class="controls__row controls__row--wrap controls__row--top">
        <Field
          :label="t('ui.controls.field.label')"
          :error="t('ui.controls.field.error')"
          label-for="kit-field-error"
          class="controls__field"
        >
          <Input
            id="kit-field-error"
            v-model="query"
            icon="search"
            clearable
            :clear-label="t('ui.controls.clear')"
          />
        </Field>
        <Input
          v-model="query"
          icon="search"
          unit="px"
          :aria-label="t('ui.controls.field.label')"
          :helper="t('ui.controls.field.helper')"
          class="controls__field"
        />
      </div>
    </div>

    <div v-if="forcedState === 'default' || isError" class="controls__block">
      <h3 class="controls__subtitle">{{ t("ui.controls.focus") }}</h3>
      <div class="controls__row controls__row--wrap">
        <Button data-testid="kit-focus-button">{{ t("ui.controls.sample.button") }}</Button>
        <IconButton
          name="search"
          :label="t('ui.controls.sample.icon')"
          data-testid="kit-focus-icon"
        />
        <Input
          v-model="query"
          :aria-label="t('ui.controls.sample.field')"
          data-testid="kit-focus-input"
        />
        <Select
          v-model="sort"
          :options="sortOptions"
          :aria-label="t('ui.controls.sample.select')"
          data-testid="kit-focus-select"
        />
        <Switch
          id="kit-focus-switch"
          v-model="switchOn"
          :label="t('ui.controls.sample.switch')"
          data-testid="kit-focus-switch"
        />
        <Checkbox
          v-model="checked"
          :label="t('ui.controls.sample.checkbox')"
          data-testid="kit-focus-checkbox"
        />
        <TextArea
          v-model="note"
          :aria-label="t('ui.controls.textarea.label')"
          :placeholder="t('ui.controls.textarea.placeholder')"
          :rows="2"
          data-testid="kit-focus-textarea"
        />
        <Slider
          v-model="page"
          :min="1"
          :max="300"
          :aria-label="t('ui.controls.slider.label')"
          :label="t('ui.controls.slider.label')"
          :show-value="true"
          class="controls__slider"
          data-testid="kit-focus-slider"
        />
      </div>
    </div>

    <div class="controls__block">
      <h3 class="controls__subtitle">{{ t("ui.controls.checkbox.indeterminate") }}</h3>
      <div class="controls__row controls__row--wrap">
        <Checkbox
          v-model="checked"
          :label="t('ui.controls.checkbox.label')"
        />
        <Checkbox
          v-model="mixed"
          indeterminate
          :label="t('ui.controls.checkbox.indeterminate')"
        />
        <Checkbox :model-value="false" :disabled="true" :label="t('ui.controls.disabled')" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.controls {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
}

.controls__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.controls__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-large);
}

.controls__lede {
  margin: 0;
  max-width: 72ch;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.controls__block {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.controls__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.controls__matrix {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.controls__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  row-gap: var(--gv-space-3);
  min-width: 0;
}

/* TextField / Select ask for 100% width; in a specimen row the cell decides. */
.controls__row > .field,
.controls__row > .select-field {
  flex: 1 1 180px;
  width: auto;
  max-width: 360px;
  min-width: 0;
}

.controls__row > .textarea-field {
  flex: 1 1 220px;
  width: auto;
  min-width: 0;
}

.controls__row--wrap {
  flex-wrap: wrap;
  row-gap: var(--gv-space-3);
}

.controls__row--top {
  align-items: flex-start;
}

.controls__row--plain {
  padding: var(--gv-space-3);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
}

.controls__row-label {
  flex: none;
  width: var(--gv-space-6);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.controls__field {
  flex: 1 1 220px;
  max-width: 320px;
}

.controls__slider {
  flex: 1 1 220px;
  max-width: 320px;
}
</style>
