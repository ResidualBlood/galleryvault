<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import { fetchCookieHealth, type CookieHealth } from "@/api/settings";
import "./messages";

const { t } = useI18n();
const health = ref<CookieHealth | null>(null);
const dismissed = ref(false);

const PROBLEM_STATES = new Set([
  "not_configured",
  "not_logged_in",
  "no_exhentai_access",
  "ip_banned",
]);

const state = computed(() => String(health.value?.state ?? "").toLowerCase());
const visible = computed(() => !dismissed.value && PROBLEM_STATES.has(state.value));

const body = computed(() => {
  if (health.value?.message) return health.value.message;
  const key = `system.global.cookie.${state.value}`;
  const translated = t(key);
  return translated === key ? t("system.global.cookie.unknown") : translated;
});

async function load(): Promise<void> {
  try {
    health.value = await fetchCookieHealth();
  } catch {
    // Advisory probe: stay silent so a failing endpoint never breaks the shell.
    health.value = null;
  }
}

onMounted(load);
</script>

<template>
  <aside
    v-if="visible"
    class="cookie-banner"
    role="status"
    data-testid="cookie-health-banner"
    :data-cookie-state="state"
  >
    <div class="cookie-banner__text">
      <strong class="cookie-banner__title">{{ t('system.global.cookie.title') }}</strong>
      <span class="cookie-banner__body">{{ body }}</span>
    </div>
    <div class="cookie-banner__actions">
      <a class="cookie-banner__link" href="#/settings">{{ t('system.global.cookie.openSettings') }}</a>
      <Button variant="text" size="compact" @click="dismissed = true">
        {{ t('system.global.cookie.dismiss') }}
      </Button>
    </div>
  </aside>
</template>

<style scoped>
.cookie-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
  padding: var(--gv-space-2) var(--gv-space-4);
  border-bottom: 1px solid var(--gv-color-warning);
  background: var(--gv-color-warning-container);
  color: var(--gv-color-on-warning-container);
}

.cookie-banner__text {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  font: var(--gv-type-body-small);
}

.cookie-banner__title {
  font: var(--gv-type-label-large);
}

.cookie-banner__body {
  overflow-wrap: anywhere;
}

.cookie-banner__actions {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  flex-shrink: 0;
}

.cookie-banner__link {
  color: var(--gv-color-on-warning-container);
  font: var(--gv-type-label-large);
  text-decoration: underline;
}

@media (max-width: 599px) {
  .cookie-banner {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
