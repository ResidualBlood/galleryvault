<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import type { IconName } from "@/components/icons/registry";
import Button from "./Button.vue";
import { ensureLayoutMessages } from "./i18n/layout";

ensureLayoutMessages();

const props = withDefaults(
  defineProps<{
    count?: number;
    label?: string;
    icon?: IconName;
    disabled?: boolean;
    testid?: string;
  }>(),
  {
    count: 0,
    label: "",
    icon: "filter",
    disabled: false,
    testid: "gv-filter-button",
  },
);

const { t } = useI18n();

const text = computed(() => props.label || t("kit.filter.label"));
const badge = computed(() => (props.count > 9 ? "9+" : String(Math.max(props.count, 0))));
const description = computed(() =>
  props.count > 0 ? `${text.value} — ${t("kit.filter.activeCount", { count: props.count })}` : text.value,
);
</script>

<template>
  <Button
    variant="outlined"
    :disabled="disabled"
    :aria-label="description"
    :data-testid="testid"
  >
    <Icon :name="icon" size="dense" />
    <span>{{ text }}</span>
    <span v-if="count > 0" class="filter__badge" data-testid="gv-filter-badge">
      {{ badge }}
    </span>
  </Button>
</template>

<style scoped>
.filter__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--gv-size-icon-sm);
  height: var(--gv-size-icon-sm);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
  font: var(--gv-type-label-small);
}
</style>
