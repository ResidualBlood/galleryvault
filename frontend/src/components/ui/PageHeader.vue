<script lang="ts">
export interface PageHeaderCrumb {
  label: string;
  to?: string;
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import Icon from "@/components/icons/Icon.vue";
import IconButton from "./IconButton.vue";
import { ensureLayoutMessages } from "./i18n/layout";
import { useI18n } from "vue-i18n";

ensureLayoutMessages();

const props = withDefaults(
  defineProps<{
    title: string;
    count?: number | string;
    countLabel?: string;
    subtitle?: string;
    crumbs?: PageHeaderCrumb[];
    back?: boolean;
    backLabel?: string;
    testid?: string;
  }>(),
  {
    count: undefined,
    countLabel: "",
    subtitle: "",
    crumbs: () => [],
    back: false,
    backLabel: "",
    testid: "gv-page-header",
  },
);

defineEmits<{ back: [] }>();

const { t } = useI18n();

const formattedCount = computed(() => {
  if (props.count === undefined || props.count === "") return "";
  if (typeof props.count === "number") return props.count.toLocaleString();
  return props.count;
});

const countDescription = computed(() => {
  if (!formattedCount.value) return "";
  return props.countLabel || t("kit.pageHeader.count", { count: formattedCount.value });
});
</script>

<template>
  <header class="page-header" :data-testid="testid">
    <nav v-if="crumbs.length" class="page-header__crumbs" :aria-label="t('kit.pageHeader.breadcrumb')">
      <template v-for="(crumb, index) in crumbs" :key="`${crumb.label}-${index}`">
        <span v-if="index > 0" class="page-header__crumb-sep" aria-hidden="true">/</span>
        <RouterLink v-if="crumb.to" class="page-header__crumb" :to="crumb.to">
          {{ crumb.label }}
        </RouterLink>
        <span v-else class="page-header__crumb page-header__crumb--current" :aria-current="index === crumbs.length - 1 ? 'page' : undefined">
          {{ crumb.label }}
        </span>
      </template>
    </nav>

    <div class="page-header__row">
      <div class="page-header__lead">
        <IconButton
          v-if="back"
          class="page-header__back"
          :label="backLabel || t('kit.pageHeader.back')"
          @click="$emit('back')"
        >
          <Icon name="back" />
        </IconButton>
        <div class="page-header__titles">
          <div class="page-header__heading">
            <h1 class="page-header__title">{{ title }}</h1>
            <span
              v-if="formattedCount"
              class="page-header__count"
              :aria-label="countDescription"
            >
              {{ formattedCount }}
            </span>
          </div>
          <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
        </div>
      </div>
      <div v-if="$slots.actions" class="page-header__actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  width: 100%;
  min-width: 0;
}

.page-header__crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.page-header__crumb {
  color: var(--gv-color-on-surface-variant);
  text-decoration: none;
}

.page-header__crumb:hover {
  color: var(--gv-color-primary-text);
}

.page-header__crumb--current {
  color: var(--gv-color-on-surface);
}

.page-header__crumb-sep {
  color: var(--gv-color-outline);
}

.page-header__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--gv-space-4);
  min-width: 0;
}

.page-header__lead {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.page-header__titles {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.page-header__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.page-header__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.page-header__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--gv-space-5);
  min-height: var(--gv-space-5);
  padding: 0 var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
  font: var(--gv-type-label-medium);
}

.page-header__subtitle {
  max-width: 72ch;
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.page-header__actions {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

@media (max-width: 599.98px) {
  .page-header__row {
    flex-direction: column;
    gap: var(--gv-space-2);
  }

  .page-header__actions {
    align-self: stretch;
    justify-content: flex-end;
  }
}
</style>
