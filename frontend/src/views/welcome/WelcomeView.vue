<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import Field from "@/components/ui/Field.vue";
import Input from "@/components/ui/Input.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Select from "@/components/ui/Select.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import BadgeStrip, { type GalleryBadge } from "@/components/gallery/BadgeStrip.vue";
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

/** Same category badge semantics as GalleryCard (fixed EH category colours). */
const CATEGORY_KEYS: Record<string, string> = {
  doujinshi: "catDoujinshi",
  manga: "catManga",
  artistcg: "catArtistcg",
  gamecg: "catGamecg",
  western: "catWestern",
  "non-h": "catNonH",
  nonh: "catNonH",
  image_set: "catImageSet",
  imageset: "catImageSet",
  cosplay: "catCosplay",
  asianporn: "catAsianporn",
  misc: "catMisc",
  other: "catMisc",
  private: "catMisc",
  deleted: "catDeleted",
};

const CATEGORY_TOKENS: Record<string, string> = {
  doujinshi: "--gv-cat-doujinshi",
  manga: "--gv-cat-manga",
  artistcg: "--gv-cat-artistcg",
  gamecg: "--gv-cat-gamecg",
  western: "--gv-cat-western",
  "non-h": "--gv-cat-nonh",
  nonh: "--gv-cat-nonh",
  image_set: "--gv-cat-imageset",
  imageset: "--gv-cat-imageset",
  cosplay: "--gv-cat-cosplay",
  asianporn: "--gv-cat-asianporn",
  misc: "--gv-cat-misc",
  other: "--gv-cat-other",
  private: "--gv-cat-private",
  deleted: "--gv-cat-other",
};

function categoryLabel(item: GalleryItem): string {
  return t(`legacy.${CATEGORY_KEYS[item.category] ?? "catMisc"}`);
}

function categoryBadge(item: GalleryItem): GalleryBadge {
  const label = categoryLabel(item);
  return {
    label,
    tone: "category",
    colorToken: CATEGORY_TOKENS[item.category] ?? "--gv-cat-misc",
    title: label,
  };
}

function endBadges(item: GalleryItem): GalleryBadge[] {
  return item.page_count > 0 ? [{ label: `${item.page_count}P` }] : [];
}

const steps = computed(() => [
  { key: "password", label: t("system.welcome.stepPassword") },
  { key: "site", label: t("system.welcome.stepSite") },
  { key: "finish", label: t("system.welcome.stepFinish") },
]);

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
</script>

<template>
  <div class="welcome" data-testid="welcome-page">
    <PageHeader
      testid="welcome-header"
      :title="t('system.welcome.title')"
      :subtitle="t('system.welcome.subtitle')"
    />

    <ol class="welcome__steps" :aria-label="t('system.welcome.stepsLabel')">
      <li v-for="(step, index) in steps" :key="step.key" class="welcome__step">
        <span class="welcome__step-index" aria-hidden="true">{{ index + 1 }}</span>
        <span class="welcome__step-label">{{ step.label }}</span>
        <Icon
          v-if="index < steps.length - 1"
          class="welcome__step-sep"
          name="chevron-right"
          size="sm"
          aria-hidden="true"
        />
      </li>
    </ol>

    <p v-if="loading" class="welcome__state">{{ t('system.common.loading') }}</p>
    <p v-else-if="loadError" class="welcome__error" role="alert">{{ loadError }}</p>

    <p v-if="pageError" class="welcome__error" role="alert" data-testid="welcome-error">
      {{ pageError }}
    </p>
    <p v-if="siteNotice" class="welcome__notice" data-testid="welcome-notice">{{ siteNotice }}</p>
    <p v-if="passwordNotice" class="welcome__notice">{{ passwordNotice }}</p>

    <section class="welcome__card" data-testid="welcome-password">
      <h2 class="welcome__card-title">
        <span class="welcome__step-badge" aria-hidden="true">1</span>
        <span>{{ t('system.welcome.stepPassword') }}</span>
      </h2>
      <p class="welcome__card-body">{{ t('system.welcome.passwordIntro') }}</p>
      <div class="welcome__fields">
        <Field :label="t('system.welcome.current')" label-for="welcome-current-password">
          <Input
            id="welcome-current-password"
            v-model="currentPassword"
            type="password"
            size="xl"
            autocomplete="current-password"
            data-testid="welcome-current-password"
          />
        </Field>
        <Field :label="t('system.welcome.next')" label-for="welcome-next-password">
          <Input
            id="welcome-next-password"
            v-model="newPassword"
            type="password"
            size="xl"
            autocomplete="new-password"
          />
        </Field>
        <Field :label="t('system.welcome.confirm')" label-for="welcome-confirm-password">
          <Input
            id="welcome-confirm-password"
            v-model="confirmPassword"
            type="password"
            size="xl"
            autocomplete="new-password"
          />
        </Field>
      </div>
      <div class="welcome__actions" data-gv-toolbar>
        <Button
          size="xl"
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
      <h2 class="welcome__card-title">
        <span class="welcome__step-badge" aria-hidden="true">2</span>
        <span>{{ t('system.welcome.stepSite') }}</span>
      </h2>
      <p class="welcome__card-body">{{ t('system.welcome.siteIntro') }}</p>

      <Field :label="t('system.welcome.baseUrl')" label-for="welcome-base-url">
        <Select
          id="welcome-base-url"
          v-model="baseUrl"
          size="xl"
          :options="baseUrlOptions"
          data-testid="welcome-base-url"
        />
      </Field>
      <Field
        v-if="customSelected"
        :label="t('system.welcome.customUrl')"
        label-for="welcome-custom-url"
      >
        <Input
          id="welcome-custom-url"
          v-model="customBaseUrl"
          size="xl"
          :placeholder="t('system.welcome.customUrl')"
        />
      </Field>

      <div class="welcome__group">
        <h3 class="welcome__group-title">{{ t('system.welcome.cookieGroup') }}</h3>
        <div class="welcome__fields">
          <Field
            :label="t('system.welcome.ipbMemberId')"
            :helper="t('system.welcome.ipbMemberIdHint')"
            label-for="welcome-ipb-member-id"
          >
            <Input
              id="welcome-ipb-member-id"
              v-model="ipbMemberId"
              type="password"
              size="xl"
              autocomplete="new-password"
            />
          </Field>
          <Field
            :label="t('system.welcome.ipbPassHash')"
            :helper="t('system.welcome.ipbPassHashHint')"
            label-for="welcome-ipb-pass-hash"
          >
            <Input
              id="welcome-ipb-pass-hash"
              v-model="ipbPassHash"
              type="password"
              size="xl"
              autocomplete="new-password"
            />
          </Field>
          <Field
            :label="t('system.welcome.igneous')"
            :helper="t('system.welcome.igneousHint')"
            label-for="welcome-igneous"
          >
            <Input
              id="welcome-igneous"
              v-model="igneous"
              type="password"
              size="xl"
              autocomplete="new-password"
            />
          </Field>
        </div>
      </div>

      <p class="welcome__hint">{{ t('system.welcome.cookiesNote') }}</p>
      <span
        class="welcome__status"
        :class="{ 'welcome__status--ok': status.exhentai_configured }"
        data-testid="welcome-site-status"
      >
        <span class="welcome__status-dot" aria-hidden="true" />
        {{
          status.exhentai_configured
            ? t('system.common.configured')
            : t('system.common.notConfigured')
        }}
      </span>
      <div class="welcome__actions" data-gv-toolbar>
        <Button
          size="xl"
          :disabled="siteBusy"
          :loading="siteBusy"
          data-testid="welcome-save-site"
          @click="saveSite"
        >
          {{ t('system.welcome.saveSite') }}
        </Button>
        <Button
          variant="outlined"
          size="xl"
          :disabled="testBusy"
          :loading="testBusy"
          data-testid="welcome-test"
          @click="testConnection"
        >
          {{ t('system.welcome.test') }}
        </Button>
      </div>
    </section>

    <section class="welcome__card" data-testid="welcome-finish">
      <h2 class="welcome__card-title">
        <span class="welcome__step-badge" aria-hidden="true">3</span>
        <span>{{ t('system.welcome.stepFinish') }}</span>
      </h2>
      <p class="welcome__card-body">
        {{ t('system.welcome.libraryCount', { count: status.library_count ?? 0 }) }}
      </p>

      <div class="welcome__actions" data-gv-toolbar>
        <Button size="xl" data-testid="welcome-finish-button" @click="finish">
          {{ t('system.welcome.finish') }}
        </Button>
        <Button
          variant="outlined"
          size="xl"
          :disabled="scanBusy"
          :loading="scanBusy"
          data-testid="welcome-scan"
          @click="scan"
        >
          {{ t('system.welcome.scan') }}
        </Button>
      </div>
      <div class="welcome__actions" data-gv-toolbar>
        <Button
          variant="outlined"
          size="xl"
          :disabled="favouritesBusy"
          :loading="favouritesBusy"
          data-testid="welcome-check-favs"
          @click="checkFavourites"
        >
          {{ t('system.welcome.checkFavs') }}
        </Button>
        <Button variant="text" size="xl" data-testid="welcome-later" @click="later">
          {{ t('system.welcome.later') }}
        </Button>
      </div>

      <h3 class="welcome__recent-title">{{ t('system.welcome.recent') }}</h3>
      <div v-if="recentLoading" class="welcome__recent">
        <Skeleton v-for="index in 4" :key="index" />
      </div>
      <ul v-else-if="recent.length" class="welcome__recent" data-testid="welcome-recent">
        <li v-for="item in recent" :key="item.id" class="welcome__recent-item">
          <a class="welcome__recent-link" :href="`#/gallery/${item.id}`">
            <span class="welcome__recent-cover">
              <img
                v-if="item.cover_url"
                class="welcome__recent-image"
                :src="item.cover_url"
                :alt="item.title"
                loading="lazy"
              />
              <span v-else class="welcome__recent-placeholder">{{ t("legacy.noCover") }}</span>
              <BadgeStrip class="welcome__recent-badges" :badges="[categoryBadge(item)]" />
              <BadgeStrip
                class="welcome__recent-badges welcome__recent-badges--end"
                :badges="endBadges(item)"
                align="end"
              />
            </span>
            <span class="welcome__recent-title-text">{{ item.title }}</span>
          </a>
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
  min-width: 0;
}

.welcome__steps {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.welcome__step {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.welcome__step-index {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-5);
  height: var(--gv-space-5);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-medium);
}

.welcome__step-sep {
  flex: none;
  color: var(--gv-color-outline);
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
  font: var(--gv-type-body-medium);
}

.welcome__notice {
  margin: 0;
  color: var(--gv-color-success);
  font: var(--gv-type-body-medium);
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
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.welcome__step-badge {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--gv-space-5);
  height: var(--gv-space-5);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
  font: var(--gv-type-label-medium);
}

.welcome__card-body {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.welcome__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--gv-space-3);
}

.welcome__group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.welcome__group-title {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.welcome__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.welcome__status {
  display: inline-flex;
  align-self: flex-start;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-chip);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.welcome__status--ok {
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
}

.welcome__status-dot {
  width: var(--gv-space-2);
  height: var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: currentColor;
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
  min-width: 0;
}

.welcome__recent-link {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface);
  text-decoration: none;
}

.welcome__recent-link:hover {
  border-color: var(--gv-color-outline);
}

.welcome__recent-cover {
  position: relative;
  display: block;
  overflow: hidden;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-lowest);
}

.welcome__recent-image {
  display: block;
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  object-fit: cover;
}

.welcome__recent-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.welcome__recent-badges {
  position: absolute;
  top: var(--gv-space-1);
  left: var(--gv-space-1);
  max-width: calc(100% - var(--gv-space-2));
}

.welcome__recent-badges--end {
  right: var(--gv-space-1);
  left: auto;
}

.welcome__recent-title-text {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

@media (max-width: 599.98px) {
  .welcome__fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
