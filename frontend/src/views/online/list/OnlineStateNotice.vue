<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import type { OnlineState } from "@/api/eh";

const props = defineProps<{ state: OnlineState }>();
defineEmits<{ retry: [] }>();

const { t } = useI18n();

const known = computed(() =>
  props.state === "auth" || props.state === "challenge" || props.state === "banned",
);

const title = computed(() => {
  if (props.state === "auth") return t("online.state.auth.title");
  if (props.state === "challenge") return t("online.state.challenge.title");
  if (props.state === "banned") return t("online.state.banned.title");
  return t("online.state.error.title");
});

const body = computed(() => {
  if (props.state === "auth") return t("online.state.auth.body");
  if (props.state === "challenge") return t("online.state.challenge.body");
  if (props.state === "banned") return t("online.state.banned.body");
  return t("online.state.error.body");
});
</script>

<template>
  <div class="online-state" :data-testid="`online-state-${state}`" :data-state="state">
    <span class="online-state__glyph" aria-hidden="true">
      {{ state === "banned" ? "⛔" : state === "auth" ? "⚿" : state === "challenge" ? "⛨" : "!" }}
    </span>
    <h2 class="online-state__title">{{ title }}</h2>
    <p class="online-state__body">{{ body }}</p>
    <div class="online-state__actions">
      <RouterLink
        v-if="state === 'auth' || state === 'challenge'"
        class="online-state__link"
        :to="{ name: 'settings' }"
        data-testid="online-state-settings"
      >
        {{ t("online.goSettings") }}
      </RouterLink>
      <Button v-if="!known" variant="outlined" data-testid="online-state-retry" @click="$emit('retry')">
        {{ t("online.retry") }}
      </Button>
    </div>
  </div>
</template>

<style scoped>
.online-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  padding: var(--gv-space-6);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
  text-align: center;
}

.online-state__glyph {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-7);
  height: var(--gv-space-7);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-warning);
  font: var(--gv-type-title-medium);
}

[data-state="banned"] .online-state__glyph {
  background: var(--gv-color-error-container);
  color: var(--gv-color-on-error-container);
}

.online-state__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.online-state__body {
  max-width: 560px;
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.online-state__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--gv-space-2);
  margin-top: var(--gv-space-2);
}

.online-state__link {
  display: inline-flex;
  align-items: center;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-5);
  border: 1px solid var(--gv-color-primary);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.online-state__link:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}
</style>
