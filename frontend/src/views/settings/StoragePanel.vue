<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import { fetchStorage, type StorageInfo, type StoragePathInfo } from "@/api/settings";
import { purgeArchivedSources } from "@/api/system";

const { t } = useI18n();
const info = ref<StorageInfo | null>(null);
const loading = ref(true);
const error = ref("");
const purgeOpen = ref(false);
const purgeBusy = ref(false);
const notice = ref("");
let timer: number | null = null;

const rows = computed(() => {
  const data = info.value ?? {};
  return [
    { key: "library", label: t("settings.storage.library"), value: data.library },
    { key: "cold", label: t("settings.storage.cold"), value: data.cold },
    { key: "downloads", label: t("settings.storage.downloads"), value: data.downloads },
    { key: "cache", label: t("settings.storage.cache"), value: data.cache },
  ];
});

function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function items(row: StoragePathInfo): string {
  if (row.gallery_count !== undefined && row.gallery_count !== null) {
    return String(row.gallery_count);
  }
  if (row.thumbnail_count !== undefined && row.thumbnail_count !== null) {
    return String(row.thumbnail_count);
  }
  return "—";
}

function status(row: StoragePathInfo): string {
  if (row.computing) return t("settings.storage.computing");
  if (row.stale) return t("settings.storage.stale");
  return "—";
}

async function load(): Promise<void> {
  try {
    info.value = await fetchStorage();
    error.value = "";
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
    schedule();
  }
}

function schedule(): void {
  if (timer !== null) {
    window.clearTimeout(timer);
    timer = null;
  }
  const data = info.value;
  const computing =
    data &&
    [data.library, data.cold, data.downloads, data.cache].some((row) => row?.computing);
  if (computing) timer = window.setTimeout(load, 3000);
}

async function purge(): Promise<void> {
  purgeBusy.value = true;
  try {
    await purgeArchivedSources();
    notice.value = t("settings.storage.purgeStarted");
    purgeOpen.value = false;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    purgeBusy.value = false;
  }
}

onMounted(load);
onBeforeUnmount(() => {
  if (timer !== null) window.clearTimeout(timer);
});
</script>

<template>
  <section class="storage" data-settings-section="storage">
    <div class="storage__head">
      <h3 class="storage__title">{{ t('settings.storage.title') }}</h3>
      <Button variant="text" size="compact" :disabled="loading" @click="load">
        {{ t('settings.storage.refresh') }}
      </Button>
    </div>

    <p v-if="error" class="storage__error" role="alert">{{ error }}</p>
    <p v-if="notice" class="storage__notice">{{ notice }}</p>

    <table class="storage__table">
      <thead>
        <tr>
          <th>{{ t('settings.storage.path') }}</th>
          <th>{{ t('settings.storage.items') }}</th>
          <th>{{ t('settings.storage.used') }}</th>
          <th>{{ t('settings.storage.status') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key" :data-storage-row="row.key">
          <td>
            <span class="storage__label">{{ row.label }}</span>
            <span class="storage__path">{{ row.value?.path || '—' }}</span>
          </td>
          <td>{{ row.value ? items(row.value) : '—' }}</td>
          <td>{{ bytes(row.value?.bytes) }}</td>
          <td>{{ row.value ? status(row.value) : '—' }}</td>
        </tr>
      </tbody>
    </table>

    <div class="storage__largest">
      <h4 class="storage__subtitle">{{ t('settings.storage.largest') }}</h4>
      <ul v-if="info?.largest?.length" class="storage__list">
        <li v-for="item in info.largest" :key="item.id" class="storage__item">
          <a class="storage__link" :href="`#/gallery/${item.id}`">{{ item.title }}</a>
          <span class="storage__meta">{{ bytes(item.storage_size) }}</span>
        </li>
      </ul>
      <p v-else class="storage__empty">{{ t('settings.storage.largestEmpty') }}</p>
    </div>

    <div class="storage__actions">
      <Button variant="outlined" data-testid="purge-sources" @click="purgeOpen = true">
        {{ t('settings.storage.purge') }}
      </Button>
    </div>

    <Dialog :open="purgeOpen" :title="t('settings.storage.purgeTitle')" @close="purgeOpen = false">
      <p class="storage__body">{{ t('settings.storage.purgeBody') }}</p>
      <template #footer>
        <Button variant="text" @click="purgeOpen = false">
          {{ t('settings.security.cancel') }}
        </Button>
        <Button variant="filled" :disabled="purgeBusy" :loading="purgeBusy" data-testid="purge-confirm" @click="purge">
          {{ t('settings.storage.purgeConfirm') }}
        </Button>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.storage {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.storage__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
}

.storage__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.storage__error {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-error);
}

.storage__notice {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-success);
}

.storage__table {
  width: 100%;
  border-collapse: collapse;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface);
}

.storage__table th {
  padding: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  text-align: left;
}

.storage__table td {
  padding: var(--gv-space-2);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  vertical-align: top;
}

.storage__label {
  display: block;
  font: var(--gv-type-label-large);
}

.storage__path {
  display: block;
  color: var(--gv-color-on-surface-variant);
  overflow-wrap: anywhere;
}

.storage__subtitle {
  margin: 0 0 var(--gv-space-2);
  font: var(--gv-type-label-large);
  color: var(--gv-color-on-surface-variant);
}

.storage__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.storage__item {
  display: flex;
  justify-content: space-between;
  gap: var(--gv-space-3);
  padding: var(--gv-space-1) 0;
  border-bottom: 1px solid var(--gv-color-outline-variant);
}

.storage__link {
  color: var(--gv-color-primary-text);
  text-decoration: none;
}

.storage__meta {
  color: var(--gv-color-on-surface-variant);
  white-space: nowrap;
}

.storage__empty {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.storage__actions {
  display: flex;
  justify-content: flex-end;
}

.storage__body {
  margin: 0;
  font: var(--gv-type-body-medium);
}
</style>
