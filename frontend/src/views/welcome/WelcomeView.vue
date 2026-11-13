<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import { changePassword, getOnboardingStatus } from "@/api/auth";
import { fetchSettings, saveSettings, testExhentai } from "@/api/settings";
import { triggerScan } from "@/api/system";
import { galleriesEp } from "@/api/galleries";
import { checkAllFavoritesEp } from "@/api/favorites";
import { request } from "@/api/client";
import { ensureSystemMessages } from "@/components/system/messages";
import type { GalleryItem } from "@/api/library";

ensureSystemMessages();

interface OnboardingStatus {
  password_default?: boolean;
  exhentai_configured?: boolean;
  library_count?: number;
}

const { t } = useI18n();
const router = useRouter();

const status = ref<OnboardingStatus>({});
const loading = ref(true);
const loadError = ref("");
const pageError = ref("");

const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const passwordBusy = ref(false);
const passwordNotice = ref("");

const baseUrl = ref("https://exhentai.org");
const customBaseUrl = ref("");
const initialBaseUrl = ref("https://exhentai.org");
const ipbMemberId = ref("");
const ipbPassHash = ref("");
const igneous = ref("");
const siteBusy = ref(false);
const siteNotice = ref("");
const testBusy = ref(false);

const scanBusy = ref(false);
const favouritesBusy = ref(false);
const recent = ref<GalleryItem[]>([]);
const recentLoading = ref(false);

const baseUrlOptions = computed(() => [
  { value: "https://exhentai.org", label: t("system.welcome.baseUrlExhentai") },
  { value: "https://e-hentai.org", label: t("system.welcome.baseUrlEhentai") },
  { value: "__custom__", label: t("system.welcome.customUrl") },
]);

const customSelected = computed(() => baseUrl.value === "__custom__");

const effectiveBaseUrl = computed(() =>
  customSelected.value ? customBaseUrl.value.trim() : baseUrl.value,
);

async function loadStatus(): Promise<void> {
  loading.value = true;
  try {
    status.value = (await getOnboardingStatus()) as OnboardingStatus;
    try {
      const settings = await fetchSettings();
      const current = String(settings.exhentai_base_url ?? "");
      if (current) {
        initialBaseUrl.value = current;
        if (current === "https://exhentai.org" || current === "https://e-hentai.org") {
          baseUrl.value = current;
        } else {
          baseUrl.value = "__custom__";
          customBaseUrl.value = current;
        }
      }
    } catch {
      /* the settings preview is best effort; defaults stay usable */
    }
    loadError.value = "";
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : t("system.welcome.loadFailed");
  } finally {
    loading.value = false;
  }
}

async function loadRecent(): Promise<void> {
  recentLoading.value = true;
  try {
    const page = await request<{ items?: GalleryItem[] }>({
      method: "GET",
      path: `${galleriesEp.path}?page_size=4`,
    });
    recent.value = Array.isArray(page.items) ? page.items.slice(0, 4) : [];
  } catch {
    recent.value = [];
  } finally {
    recentLoading.value = false;
  }
}

onMounted(() => {
  void loadStatus().then(() => loadRecent());
});

async function savePassword(): Promise<void> {
  pageError.value = "";
  passwordNotice.value = "";
  if (!currentPassword.value || !newPassword.value) {
    pageError.value = t("system.welcome.passwordRequired");
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    pageError.value = t("system.welcome.passwordMismatch");
    return;
  }
  passwordBusy.value = true;
  try {
    await changePassword(currentPassword.value, newPassword.value);
    currentPassword.value = "";
    newPassword.value = "";
    confirmPassword.value = "";
    passwordNotice.value = t("system.welcome.passwordOk");
    await loadStatus();
  } catch (cause) {
    pageError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    passwordBusy.value = false;
  }
}

async function saveSite(): Promise<void> {
  pageError.value = "";
  siteNotice.value = "";
  const payload: Record<string, unknown> = {};
  const url = effectiveBaseUrl.value;
  if (!url) {
    pageError.value = t("settings.error.baseUrl");
    return;
  }
  if (url !== initialBaseUrl.value) payload.exhentai_base_url = url;
  if (ipbMemberId.value.trim()) payload.ipb_member_id = ipbMemberId.value.trim();
  if (ipbPassHash.value.trim()) payload.ipb_pass_hash = ipbPassHash.value.trim();
  if (igneous.value.trim()) payload.igneous = igneous.value.trim();
  if (!Object.keys(payload).length) {
    siteNotice.value = t("system.welcome.noChanges");
    return;
  }
  siteBusy.value = true;
  try {
    await saveSettings(payload);
    initialBaseUrl.value = url;
    ipbMemberId.value = "";
    ipbPassHash.value = "";
    igneous.value = "";
    siteNotice.value = t("system.welcome.saved");
    await loadStatus();
  } catch (cause) {
    pageError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    siteBusy.value = false;
  }
}

async function testConnection(): Promise<void> {
  testBusy.value = true;
  pageError.value = "";
  try {
    const result = await testExhentai();
    siteNotice.value = result.message || result.status || t("system.welcome.testOk");
  } catch (cause) {
    pageError.value = cause instanceof Error ? cause.message : t("system.welcome.testFail");
  } finally {
    testBusy.value = false;
  }
}

async function scan(): Promise<void> {
  scanBusy.value = true;
  try {
    await triggerScan();
    siteNotice.value = t("system.welcome.scanStarted");
  } catch (cause) {
    pageError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    scanBusy.value = false;
  }
}

async function checkFavourites(): Promise<void> {
  favouritesBusy.value = true;
  try {
    await request(checkAllFavoritesEp, { body: {} });
    siteNotice.value = t("system.welcome.checkStarted");
  } catch (cause) {
    pageError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    favouritesBusy.value = false;
  }
}

async function finish(): Promise<void> {
  pageError.value = "";
  try {
    const latest = (await getOnboardingStatus()) as OnboardingStatus;
    status.value = latest;
    if (latest.password_default) {
      pageError.value = t("system.welcome.finishBlocked");
      return;
    }
  } catch {
    /* status is best effort; allow finishing */
  }
  await router.push({ name: "browse" });
}

function later(): void {
  void router.push({ name: "browse" });
}

function galleryThumb(item: GalleryItem): string {
  return item.cover_url ?? "";
}
</script>

<template>
  <div class="welcome" data-testid="welcome-page">
    <header class="welcome__header">
      <h1 class="welcome__title">{{ t('system.welcome.title') }}</h1>
      <p class="welcome__subtitle">{{ t('system.welcome.subtitle') }}</p>
    </header>

    <p v-if="loading" class="welcome__state">{{ t('system.common.loading') }}</p>
    <p v-else-if="loadError" class="welcome__error" role="alert">{{ loadError }}</p>

    <p v-if="pageError" class="welcome__error" role="alert" data-testid="welcome-error">
      {{ pageError }}
    </p>
    <p v-if="siteNotice" class="welcome__notice" data-testid="welcome-notice">{{ siteNotice }}</p>
    <p v-if="passwordNotice" class="welcome__notice">{{ passwordNotice }}</p>

    <section class="welcome__card" data-testid="welcome-password">
      <h2 class="welcome__card-title">{{ t('system.welcome.stepPassword') }}</h2>
      <p class="welcome__card-body">{{ t('system.welcome.passwordIntro') }}</p>
      <div class="welcome__grid">
        <Input
          v-model="currentPassword"
          type="password"
          autocomplete="current-password"
          :label="t('system.welcome.current')"
          data-testid="welcome-current-password"
        />
        <Input
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          :label="t('system.welcome.next')"
        />
        <Input
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          :label="t('system.welcome.confirm')"
        />
      </div>
      <div class="welcome__actions">
        <Button
          :disabled="passwordBusy"
          :loading="passwordBusy"
          data-testid="welcome-save-password"
          @click="savePassword"
        >
          {{ t('system.welcome.savePassword') }}
        </Button>
      </div>
    </section>

    <section class="welcome__card" data-testid="welcome-site">
      <h2 class="welcome__card-title">{{ t('system.welcome.stepSite') }}</h2>
      <p class="welcome__card-body">{{ t('system.welcome.siteIntro') }}</p>
      <div class="welcome__grid">
        <Select
          v-model="baseUrl"
          :options="baseUrlOptions"
          :label="t('system.welcome.baseUrl')"
          data-testid="welcome-base-url"
        />
        <Input
          v-if="customSelected"
          v-model="customBaseUrl"
          :label="t('system.welcome.customUrl')"
          :placeholder="t('system.welcome.customUrl')"
        />
        <Input
          v-model="ipbMemberId"
          type="password"
          autocomplete="new-password"
          :label="t('system.welcome.ipbMemberId')"
        />
        <Input
          v-model="ipbPassHash"
          type="password"
          autocomplete="new-password"
          :label="t('system.welcome.ipbPassHash')"
        />
        <Input
          v-model="igneous"
          type="password"
          autocomplete="new-password"
          :label="t('system.welcome.igneous')"
        />
      </div>
      <p class="welcome__hint">{{ t('system.welcome.cookiesNote') }}</p>
      <div class="welcome__actions">
        <Button
          :disabled="siteBusy"
          :loading="siteBusy"
          data-testid="welcome-save-site"
          @click="saveSite"
        >
          {{ t('system.welcome.saveSite') }}
        </Button>
        <Button
          variant="outlined"
          :disabled="testBusy"
          :loading="testBusy"
          data-testid="welcome-test"
          @click="testConnection"
        >
          {{ t('system.welcome.test') }}
        </Button>
        <span class="welcome__status">
          {{
            status.exhentai_configured
              ? t('system.common.configured')
              : t('system.common.notConfigured')
          }}
        </span>
      </div>
    </section>

    <section class="welcome__card" data-testid="welcome-finish">
      <h2 class="welcome__card-title">{{ t('system.welcome.stepFinish') }}</h2>
      <p class="welcome__card-body">
        {{ t('system.welcome.libraryCount', { count: status.library_count ?? 0 }) }}
      </p>

      <div class="welcome__actions">
        <Button
          variant="outlined"
          :disabled="scanBusy"
          :loading="scanBusy"
          data-testid="welcome-scan"
          @click="scan"
        >
          {{ t('system.welcome.scan') }}
        </Button>
        <Button
          variant="outlined"
          :disabled="favouritesBusy"
          :loading="favouritesBusy"
          data-testid="welcome-check-favs"
          @click="checkFavourites"
        >
          {{ t('system.welcome.checkFavs') }}
        </Button>
        <Button data-testid="welcome-finish-button" @click="finish">
          {{ t('system.welcome.finish') }}
        </Button>
        <Button variant="text" data-testid="welcome-later" @click="later">
          {{ t('system.welcome.later') }}
        </Button>
      </div>

      <h3 class="welcome__recent-title">{{ t('system.welcome.recent') }}</h3>
      <div v-if="recentLoading" class="welcome__recent">
        <Skeleton v-for="index in 4" :key="index" />
      </div>
      <ul v-else-if="recent.length" class="welcome__recent" data-testid="welcome-recent">
        <li v-for="item in recent" :key="item.id" class="welcome__recent-item">
          <img
            v-if="galleryThumb(item)"
            class="welcome__thumb"
            :src="galleryThumb(item)"
            :alt="item.title"
            loading="lazy"
          />
          <a class="welcome__recent-title-text" :href="`#/gallery/${item.id}`">{{ item.title }}</a>
        </li>
      </ul>
      <p v-else class="welcome__hint">{{ t('system.welcome.recentEmpty') }}</p>
    </section>
  </div>
</template>

<style scoped>
.welcome {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  padding: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.welcome__title {
  margin: 0;
  font: var(--gv-type-headline-medium);
  color: var(--gv-color-on-surface);
}

.welcome__subtitle {
  margin: var(--gv-space-1) 0 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.welcome__state,
.welcome__hint {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.welcome__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.welcome__notice {
  margin: 0;
  color: var(--gv-color-success);
  font: var(--gv-type-body-small);
}

.welcome__card {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.welcome__card-title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-primary-text);
}

.welcome__card-body {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.welcome__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--gv-space-3);
}

.welcome__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.welcome__status {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.welcome__recent-title {
  margin: var(--gv-space-2) 0 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.welcome__recent {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--gv-space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.welcome__recent-item {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.welcome__thumb {
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  object-fit: cover;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-lowest);
}

.welcome__recent-title-text {
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  text-decoration: none;
}

@media (max-width: 599px) {
  .welcome {
    padding: var(--gv-space-3);
  }
}
</style>
