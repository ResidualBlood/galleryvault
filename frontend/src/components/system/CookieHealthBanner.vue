<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import { fetchCookieHealth, type CookieHealth } from "@/api/settings";
import "./messages";

const { t } = useI18n();
const router = useRouter();
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

function openSettings(): void {
  void router.push({ name: "settings" });
}

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
      <Icon class="cookie-banner__icon" name="status-warning" size="md" />
      <strong class="cookie-banner__title">{{ t('system.global.cookie.title') }}</strong>
      <span class="cookie-banner__body">{{ body }}</span>
    </div>
    <div class="cookie-banner__actions" data-gv-toolbar>
      <Button variant="text" data-testid="cookie-banner-settings" @click="openSettings">
        {{ t('system.global.cookie.openSettings') }}
      </Button>
      <Button variant="text" data-testid="cookie-banner-dismiss" @click="dismissed = true">
        <Icon name="close" size="dense" />
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
  min-width: 0;
  align-items: center;
  gap: var(--gv-space-2);
  font: var(--gv-type-body-small);
}

.cookie-banner__icon {
  flex: none;
}

.cookie-banner__title {
  flex: none;
  font: var(--gv-type-label-large);
  white-space: nowrap;
}

.cookie-banner__body {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cookie-banner__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-1);
}

/* SH-07: on 390 the banner used to take 100px (12% of the viewport) with a
   14px title over 12px body. Keep one line: title + the two 40px actions. */
@media (max-width: 599px) {
  .cookie-banner {
    gap: var(--gv-space-2);
    padding: var(--gv-space-1) var(--gv-space-3);
  }

  .cookie-banner__title {
    flex: 0 1 auto;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .cookie-banner__body {
    display: none;
  }
}
</style>
