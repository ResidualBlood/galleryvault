<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import PasswordSection from "./PasswordSection.vue";
import ApiTokenSection from "./ApiTokenSection.vue";
import SettingsGroupPanel from "./SettingsGroupPanel.vue";
import StoragePanel from "./StoragePanel.vue";
import { ensureSettingsMessages } from "./messages";
import {
  ALL_FIELDS,
  SECURITY_SENSITIVE_KEYS,
  SETTINGS_GROUPS,
  fieldByKey,
  searchSettings,
} from "./schema";
import {
  controlValue,
  readPreference,
  writePreference,
} from "./preferences";
import {
  buildBaseline,
  canSubmit,
  computeGroupSave,
  type GroupSavePlan,
} from "./save";
import {
  fetchSettings,
  fetchThumbsStatus,
  fetchTagSearchStatus,
  generateThumbnails,
  reloadTagTranslation,
  repairTagCategories,
  opdsEp,
  saveSettings,
  startTagSync,
  testExhentai,
  testTelegram,
  type AppSettings,
  type TagSearchStatus,
  type ThumbsStatus,
} from "@/api/settings";
import { fetchFavoriteCategories } from "@/api/favorites";
import { fetchPause, purgeArchivedSources, setPaused } from "@/api/system";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";

ensureSettingsMessages();

const groups = SETTINGS_GROUPS;
const BASE_URL_VALUES = ["https://exhentai.org", "https://e-hentai.org"];

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const ui = useUiStore();

const activeId = ref(groups[0].id);
const mobileDetail = ref(false);
const search = ref("");
const server = ref<AppSettings>({});
const baselines = ref<Record<string, Record<string, unknown>>>({});
const draft = reactive<Record<string, unknown>>({});
const aux = reactive<Record<string, unknown>>({});
const customBaseUrl = ref("");
const baselineCustomBaseUrl = ref("");
const loading = ref(true);
const loaded = ref(false);
const loadError = ref("");
const saving = ref(false);
const saveError = ref("");
const confirmOpen = ref(false);
const confirmPassword = ref("");
const confirmBusy = ref(false);
const confirmError = ref("");
const pendingPlan = ref<GroupSavePlan | null>(null);
const purgeOpen = ref(false);
const purgeBusy = ref(false);

const activeGroup = computed(() => groups.find((group) => group.id === activeId.value) ?? groups[0]);
const searchHits = computed(() => searchSettings(search.value));

function readPreferences(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of ALL_FIELDS) {
    if (field.storage === "ls") out[field.key] = readPreference(field.key);
  }
  return out;
}

function makeBaseline(
  groupId: string,
  preferences: Record<string, unknown>,
): Record<string, unknown> {
  const group = groups.find((entry) => entry.id === groupId);
  if (!group) return {};
  const baseline = buildBaseline(group, server.value, preferences, controlValue);
  if (baseline.exhentai_base_url !== undefined) {
    const value = String(baseline.exhentai_base_url);
    if (!BASE_URL_VALUES.includes(value)) {
      baseline.exhentai_base_url = "__custom__";
    }
  }
  return baseline;
}

function resetDrafts(): void {
  const preferences = readPreferences();
  for (const field of ALL_FIELDS) {
    if (field.storage === "ls") {
      draft[field.key] = controlValue(field, preferences[field.key] ?? field.default);
    } else if (field.storage === "us" && field.control === "secret") {
      draft[field.key] = "";
    } else if (field.storage === "us") {
      draft[field.key] = controlValue(field, server.value[field.key] ?? field.default);
    } else if (field.storage === "readonly" && field.source === "server") {
      draft[field.key] = server.value[field.key] ?? "";
    } else if (field.control === "readonly" || field.control === "link") {
      draft[field.key] = undefined;
    }
  }
  const baseUrl = String(server.value.exhentai_base_url ?? "");
  if (baseUrl && !BASE_URL_VALUES.includes(baseUrl)) {
    customBaseUrl.value = baseUrl;
    baselineCustomBaseUrl.value = baseUrl;
  } else {
    customBaseUrl.value = "";
    baselineCustomBaseUrl.value = "";
  }
  const next: Record<string, Record<string, unknown>> = {};
  for (const group of groups) next[group.id] = makeBaseline(group.id, preferences);
  baselines.value = next;
}

const plans = computed<Record<string, GroupSavePlan>>(() => {
  const out: Record<string, GroupSavePlan> = {};
  for (const group of groups) {
    out[group.id] = computeGroupSave(group, draft, baselines.value[group.id] ?? {}, {
      customBaseUrl: customBaseUrl.value,
      baselineCustomBaseUrl: baselineCustomBaseUrl.value,
    });
  }
  return out;
});

const activePlan = computed<GroupSavePlan | undefined>(() => plans.value[activeId.value]);
const activeDirty = computed(() => Boolean(activePlan.value?.changedKeys.length));

const configured = computed<Record<string, boolean>>(() => {
  const names = Array.isArray(server.value.exhentai_cookie_names)
    ? (server.value.exhentai_cookie_names as unknown[]).map((entry) => String(entry))
    : [];
  return {
    ipb_member_id: names.includes("ipb_member_id"),
    ipb_pass_hash: names.includes("ipb_pass_hash"),
    igneous: names.includes("igneous"),
    telegram_bot_token: Boolean(server.value.telegram_bot_configured),
  };
});

function thumbsText(status: ThumbsStatus | undefined): string {
  if (!status) return "";
  if (status.running) return t("settings.status.running");
  if (status.completed_at === undefined || status.completed_at === null) {
    return t("settings.status.never");
  }
  return t("settings.status.thumbs", {
    succeeded: status.succeeded ?? 0,
    failed: status.failed ?? 0,
  });
}

function translationText(status: TagSearchStatus | undefined): string {
  if (!status) return "";
  if (status.last_error) {
    return t("settings.status.translationError", { error: status.last_error });
  }
  if (typeof status.entries === "number") {
    return t("settings.status.translation", { entries: status.entries });
  }
  return t("settings.status.unknown");
}

const display = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {
    thumbnail_status: thumbsText(aux.thumbnail_status as ThumbsStatus | undefined),
    translation_status: translationText(aux.translation_status as TagSearchStatus | undefined),
  };
  const categories = aux.favorites_categories;
  if (Array.isArray(categories)) {
    const enabled = categories.filter(
      (entry) => entry && typeof entry === "object" && (entry as { enabled?: boolean }).enabled,
    ).length;
    out.favorites_categories = t("settings.status.favorites", {
      enabled,
      total: categories.length,
    });
  }
  if (typeof window !== "undefined") {
    out.integration_opds_url = `${window.location.origin}${opdsEp.path}`;
  }
  return out;
});

async function loadAux(): Promise<void> {
  await Promise.allSettled([
    fetchThumbsStatus().then((value) => {
      aux.thumbnail_status = value;
    }),
    fetchTagSearchStatus().then((value) => {
      aux.translation_status = value;
    }),
    fetchFavoriteCategories().then((value) => {
      aux.favorites_categories = value;
    }),
  ]);
}

async function load(): Promise<void> {
  if (!loaded.value) loading.value = true;
  loadError.value = "";
  try {
    const data = await fetchSettings();
    try {
      const pause = await fetchPause();
      data.global_paused = pause.paused;
    } catch {
      data.global_paused = false;
    }
    server.value = data;
    resetDrafts();
    loaded.value = true;
    void loadAux();
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : t("settings.loadFailed");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function selectGroup(id: string): void {
  activeId.value = id;
  mobileDetail.value = true;
  saveError.value = "";
}

function backToGroups(): void {
  mobileDetail.value = false;
}

function openHit(groupId: string, key: string): void {
  activeId.value = groupId;
  mobileDetail.value = true;
  search.value = "";
  void nextTick(() => {
    const row = document.querySelector(`[data-setting-key="${key}"]`);
    if (row instanceof HTMLElement) row.scrollIntoView({ block: "center" });
  });
}

function onRowUpdate(key: string, value: unknown): void {
  if (key === "global_paused") {
    void togglePause(Boolean(value));
    return;
  }
  onUpdate(key, value);
}

function onUpdate(key: string, value: unknown): void {
  draft[key] = value;
  const field = fieldByKey(key);
  if (field?.storage === "ls") {
    try {
      writePreference(key, value);
    } catch {
      /* storage may be blocked; the draft still drives this session */
    }
  }
}

async function togglePause(next: boolean): Promise<void> {
  draft.global_paused = next;
  try {
    const result = await setPaused(next);
    draft.global_paused = result.paused;
    baselines.value = {
      ...baselines.value,
      download: { ...(baselines.value.download ?? {}), global_paused: result.paused },
    };
  } catch {
    draft.global_paused = !next;
    ui.error(t("settings.error.pauseFailed"));
  }
}

function fieldError(plan: GroupSavePlan): string {
  const first = plan.errors[0];
  return first ? t(first.messageKey) : "";
}

async function saveActive(): Promise<void> {
  const plan = activePlan.value;
  if (!plan) return;
  saveError.value = "";
  if (plan.errors.length) {
    saveError.value = fieldError(plan);
    return;
  }
  if (!plan.changedKeys.length) return;
  if (plan.requiresConfirmation) {
    pendingPlan.value = plan;
    confirmPassword.value = "";
    confirmError.value = "";
    confirmOpen.value = true;
    return;
  }
  if (!canSubmit(plan, false)) return;
  await submitPlan(plan);
}

async function submitPlan(plan: GroupSavePlan, password = ""): Promise<void> {
  saving.value = true;
  confirmBusy.value = Boolean(password);
  try {
    await saveSettings(plan.payload, password);
    confirmOpen.value = false;
    pendingPlan.value = null;
    confirmPassword.value = "";
    await load();
    ui.success(t("settings.saved"));
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 428) {
      if (password) {
        confirmError.value = t("settings.security.wrong");
      } else {
        pendingPlan.value = plan;
        confirmPassword.value = "";
        confirmError.value = "";
        confirmOpen.value = true;
      }
      return;
    }
    const message = cause instanceof Error ? cause.message : t("settings.error.saveFailed");
    if (password) confirmError.value = message;
    else saveError.value = message;
  } finally {
    saving.value = false;
    confirmBusy.value = false;
  }
}

async function confirmSave(): Promise<void> {
  if (!pendingPlan.value) return;
  if (!confirmPassword.value) {
    confirmError.value = t("settings.security.password");
    return;
  }
  confirmError.value = "";
  await submitPlan(pendingPlan.value, confirmPassword.value);
}

function discard(): void {
  saveError.value = "";
  resetDrafts();
}

function securityKeys(plan: GroupSavePlan | null): string {
  if (!plan) return "";
  return plan.changedKeys
    .filter((key) => SECURITY_SENSITIVE_KEYS.includes(key))
    .join(", ");
}

async function handleAction(actionId: string): Promise<void> {
  const action = activeGroup.value.actions.find((entry) => entry.id === actionId);
  if (!action) return;
  saveError.value = "";
  try {
    switch (action.kind) {
      case "eh-test": {
        const result = await testExhentai();
        ui.success(result.message || result.status || "OK");
        break;
      }
      case "gen-thumbs": {
        const result = await generateThumbnails();
        ui.success(`${t("settings.action.genThumbs")}${result.queued ? ` (${result.queued})` : ""}`);
        await loadAux();
        break;
      }
      case "sync-all-tags": {
        const result = await startTagSync();
        ui.success(`${t("settings.action.syncAllTags")}${result.queued ? ` (${result.queued})` : ""}`);
        break;
      }
      case "force-update-translation": {
        const result = await reloadTagTranslation();
        ui.success(`${t("settings.action.forceUpdateTranslation")}${result.ok ? " OK" : ""}`);
        await loadAux();
        break;
      }
      case "repair-categories": {
        const result = await repairTagCategories();
        ui.success(
          `${t("settings.action.repairCategories")}: ${result.repaired ?? 0}/${result.total ?? 0}`,
        );
        await loadAux();
        break;
      }
      case "test-telegram": {
        const result = await testTelegram();
        ui.success(result.ok ? `${t("settings.action.testTelegram")} OK` : JSON.stringify(result.results ?? {}));
        break;
      }
      case "purge-sources":
        purgeOpen.value = true;
        break;
      case "logout":
        await auth.logout();
        await router.replace({ name: "login" });
        break;
      default:
        break;
    }
  } catch (cause) {
    saveError.value = cause instanceof Error ? cause.message : String(cause);
  }
}

async function confirmPurge(): Promise<void> {
  purgeBusy.value = true;
  try {
    await purgeArchivedSources();
    purgeOpen.value = false;
    ui.success(t("settings.storage.purgeStarted"));
  } catch (cause) {
    saveError.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    purgeBusy.value = false;
  }
}

defineExpose({ plans });
</script>

<template>
  <div class="settings" data-testid="settings-page">
    <header class="settings__header">
      <div>
        <h1 class="settings__title">{{ t('settings.title') }}</h1>
        <p class="settings__subtitle">{{ t('settings.subtitle') }}</p>
      </div>
    </header>

    <div class="settings__search">
      <Input
        v-model="search"
        type="search"
        :placeholder="t('settings.searchPlaceholder')"
        data-testid="settings-search"
      />
    </div>

    <div v-if="loading" class="settings__state">{{ t('settings.saving') }}</div>
    <div v-else-if="loadError" class="settings__state settings__state--error" role="alert">
      <p>{{ loadError }}</p>
      <Button variant="outlined" @click="load">{{ t('settings.retry') }}</Button>
    </div>

    <div v-else-if="search.trim()" class="settings__results" data-testid="settings-search-results">
      <p v-if="!searchHits.length" class="settings__state" data-testid="settings-search-empty">
        {{ t('settings.searchEmpty') }}
      </p>
      <ul v-else class="settings__result-list">
        <li v-for="hit in searchHits" :key="`${hit.group.id}:${hit.field.key}`">
          <button
            type="button"
            class="settings__result"
            :data-result-key="hit.field.key"
            @click="openHit(hit.group.id, hit.field.key)"
          >
            <span class="settings__result-label">{{ t(hit.field.labelKey) }}</span>
            <span class="settings__result-group">{{ t(hit.group.titleKey) }}</span>
            <code class="settings__result-key">{{ hit.field.key }}</code>
          </button>
        </li>
      </ul>
    </div>

    <div v-else class="settings__layout">
      <nav
        class="settings__nav"
        :class="{ 'settings__nav--hidden': mobileDetail }"
        data-testid="settings-nav"
      >
        <p class="settings__nav-title">{{ t('settings.groups') }}</p>
        <button
          v-for="group in groups"
          :key="group.id"
          type="button"
          class="settings__nav-item"
          :class="{ 'settings__nav-item--active': group.id === activeId }"
          :data-settings-nav="group.id"
          :aria-current="group.id === activeId ? 'page' : undefined"
          @click="selectGroup(group.id)"
        >
          <span>{{ t(group.titleKey) }}</span>
          <span v-if="plans[group.id]?.changedKeys.length" class="settings__nav-dot" aria-hidden="true" />
        </button>
      </nav>

      <main
        class="settings__content"
        :class="{ 'settings__content--hidden': !mobileDetail }"
        data-testid="settings-content"
      >
        <button
          type="button"
          class="settings__back"
          data-testid="settings-back"
          @click="backToGroups"
        >
          ← {{ t('settings.back') }}
        </button>

        <SettingsGroupPanel
          :group="activeGroup"
          :values="draft"
          :custom-base-url="customBaseUrl"
          :configured="configured"
          :display="display"
          @update="onRowUpdate"
          @update:custom-base-url="customBaseUrl = $event"
          @action="handleAction"
        />

        <template v-if="activeGroup.id === 'account'">
          <PasswordSection @changed="ui.success(t('settings.password.changed'))" />
          <ApiTokenSection />
        </template>

        <StoragePanel v-if="activeGroup.id === 'system'" />

        <p v-if="saveError" class="settings__error" role="alert" data-testid="settings-error">
          {{ saveError }}
        </p>

        <div v-if="activeDirty" class="settings__savebar" data-testid="settings-savebar">
          <span class="settings__savebar-text">{{ t('settings.unsaved') }}</span>
          <Button variant="text" size="compact" :disabled="saving" @click="discard">
            {{ t('settings.discard') }}
          </Button>
          <Button
            size="compact"
            :loading="saving"
            :disabled="saving"
            data-testid="settings-save"
            @click="saveActive"
          >
            {{ saving ? t('settings.saving') : t('settings.save') }}
          </Button>
        </div>
      </main>
    </div>

    <Dialog
      :open="confirmOpen"
      :title="t('settings.security.title')"
      testid="security-confirm"
      @close="confirmOpen = false"
    >
      <p class="settings__dialog-body">
        {{ t('settings.security.body', { keys: securityKeys(pendingPlan) }) }}
      </p>
      <Input
        v-model="confirmPassword"
        type="password"
        autocomplete="current-password"
        :label="t('settings.security.password')"
        data-testid="security-password"
        @enter="confirmSave"
      />
      <p v-if="confirmError" class="settings__error" role="alert">{{ confirmError }}</p>
      <template #footer>
        <Button variant="text" @click="confirmOpen = false">
          {{ t('settings.security.cancel') }}
        </Button>
        <Button
          :loading="confirmBusy"
          :disabled="confirmBusy"
          data-testid="security-confirm-submit"
          @click="confirmSave"
        >
          {{ t('settings.security.submit') }}
        </Button>
      </template>
    </Dialog>

    <Dialog :open="purgeOpen" :title="t('settings.storage.purgeTitle')" @close="purgeOpen = false">
      <p class="settings__dialog-body">{{ t('settings.storage.purgeBody') }}</p>
      <template #footer>
        <Button variant="text" @click="purgeOpen = false">
          {{ t('settings.security.cancel') }}
        </Button>
        <Button :loading="purgeBusy" :disabled="purgeBusy" data-testid="settings-purge-confirm" @click="confirmPurge">
          {{ t('settings.storage.purgeConfirm') }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  padding: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.settings__header {
  display: flex;
  justify-content: space-between;
  gap: var(--gv-space-4);
}

.settings__title {
  margin: 0;
  font: var(--gv-type-headline-medium);
  color: var(--gv-color-on-surface);
}

.settings__subtitle {
  margin: var(--gv-space-1) 0 0;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

.settings__search {
  max-width: 520px;
}

.settings__state {
  padding: var(--gv-space-4);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
}

.settings__state--error {
  color: var(--gv-color-error);
}

.settings__results {
  padding: var(--gv-space-2) 0;
}

.settings__result-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.settings__result {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-3);
  width: 100%;
  min-height: var(--gv-size-touch);
  padding: var(--gv-space-2) var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface);
  text-align: left;
  cursor: pointer;
}

.settings__result:hover {
  background: var(--gv-color-surface-container-high);
}

.settings__result-label {
  font: var(--gv-type-body-large);
}

.settings__result-group {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-body-small);
}

.settings__result-key {
  margin-left: auto;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.settings__layout {
  display: grid;
  grid-template-columns: var(--gv-size-drawer-width) minmax(0, 1fr);
  gap: var(--gv-space-4);
  align-items: start;
}

.settings__nav {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-low);
  position: sticky;
  top: var(--gv-space-4);
}

.settings__nav-title {
  margin: 0;
  padding: var(--gv-space-1) var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.settings__nav-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-3);
  border: none;
  border-radius: var(--gv-radius-full);
  background: transparent;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  text-align: left;
  cursor: pointer;
}

.settings__nav-item:hover {
  background: var(--gv-color-surface-container-high);
}

.settings__nav-item--active {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.settings__nav-dot {
  width: var(--gv-space-2);
  height: var(--gv-space-2);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
}

.settings__content {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  min-width: 0;
}

.settings__back {
  display: none;
  align-self: flex-start;
  min-height: var(--gv-size-touch);
  padding: 0 var(--gv-space-2);
  border: none;
  background: transparent;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  cursor: pointer;
}

.settings__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.settings__savebar {
  position: sticky;
  bottom: var(--gv-space-2);
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-3) var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-highest);
  box-shadow: var(--gv-elev-3);
}

.settings__savebar-text {
  flex: 1;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.settings__dialog-body {
  margin: 0 0 var(--gv-space-3);
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface-variant);
}

@media (max-width: 839px) {
  .settings {
    padding: var(--gv-space-3);
  }

  .settings__layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .settings__nav--hidden {
    display: none;
  }

  .settings__content--hidden {
    display: none;
  }

  .settings__back {
    display: inline-flex;
    align-items: center;
  }
}
</style>
