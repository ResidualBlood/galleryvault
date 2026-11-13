<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import {
  clearNotifications,
  getNotifications,
  markNotificationsRead,
  type NotificationItem,
} from "@/api/system";
import { ApiError } from "@/api/client";
import "./messages";

const props = withDefaults(
  defineProps<{
    pollMs?: number;
  }>(),
  {
    pollMs: 30000,
  },
);

const { t } = useI18n();
const items = ref<NotificationItem[]>([]);
const unread = ref(0);
const loading = ref(false);
const error = ref("");
let timer: number | null = null;

const sorted = computed(() =>
  [...items.value].sort((a, b) => {
    const left = a.created_at ? Date.parse(a.created_at) : 0;
    const right = b.created_at ? Date.parse(b.created_at) : 0;
    return right - left;
  }),
);

function apply(data: { items?: NotificationItem[]; unread_count?: number; unread?: number }): void {
  items.value = Array.isArray(data.items) ? data.items : [];
  unread.value = data.unread_count ?? data.unread ?? 0;
}

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true;
  try {
    apply(await getNotifications());
    error.value = "";
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 401)) {
      error.value = cause instanceof Error ? cause.message : t("system.notifications.loadFailed");
    }
  } finally {
    loading.value = false;
  }
}

async function markRead(): Promise<void> {
  try {
    apply(await markNotificationsRead());
  } catch {
    error.value = t("system.notifications.readFailed");
  }
}

async function clearAll(): Promise<void> {
  try {
    apply(await clearNotifications());
  } catch {
    error.value = t("system.notifications.clearFailed");
  }
}

function formatTime(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

onMounted(() => {
  void load();
  if (props.pollMs > 0) {
    timer = window.setInterval(() => void load(true), props.pollMs);
  }
});

onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer);
});
</script>

<template>
  <section class="notifications" data-testid="notification-panel">
    <header class="notifications__head">
      <div class="notifications__title-line">
        <h2 class="notifications__title">{{ t('system.notifications.title') }}</h2>
        <span v-if="unread" class="notifications__badge" data-testid="notification-badge">
          {{ unread }}
        </span>
        <span v-if="unread" class="notifications__unread">
          {{ t('system.notifications.unread', { count: unread }) }}
        </span>
      </div>
      <div class="notifications__actions">
        <Button variant="text" size="compact" :disabled="loading" @click="load()">
          {{ t('system.notifications.refresh') }}
        </Button>
        <Button variant="text" size="compact" :disabled="!unread" @click="markRead">
          {{ t('system.notifications.markRead') }}
        </Button>
        <Button variant="text" size="compact" :disabled="!items.length" @click="clearAll">
          {{ t('system.notifications.clear') }}
        </Button>
      </div>
    </header>

    <p v-if="error" class="notifications__error" role="alert">{{ error }}</p>
    <p v-if="!sorted.length && !error" class="notifications__empty">
      {{ t('system.notifications.empty') }}
    </p>

    <ul v-else class="notifications__list">
      <li
        v-for="item in sorted"
        :key="item.id"
        class="notifications__item"
        :class="{ 'notifications__item--unread': !item.read }"
        :data-notification-id="item.id"
      >
        <div class="notifications__item-head">
          <span class="notifications__item-title">{{ item.title }}</span>
          <span class="notifications__time">{{ formatTime(item.created_at) }}</span>
        </div>
        <p v-if="item.detail" class="notifications__detail">{{ item.detail }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.notifications {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  width: min(420px, calc(100vw - var(--gv-space-6)));
  max-height: 70vh;
  overflow: auto;
  padding: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-high);
  box-shadow: var(--gv-elev-3);
}

.notifications__head {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.notifications__title-line {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  flex-wrap: wrap;
}

.notifications__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.notifications__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--gv-space-5);
  height: var(--gv-space-5);
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-primary);
  color: var(--gv-color-on-primary);
  font: var(--gv-type-label-small);
}

.notifications__unread {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.notifications__actions {
  display: flex;
  gap: var(--gv-space-1);
  flex-wrap: wrap;
}

.notifications__error {
  margin: 0;
  color: var(--gv-color-error);
  font: var(--gv-type-body-small);
}

.notifications__empty {
  margin: 0;
  padding: var(--gv-space-3);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
  text-align: center;
}

.notifications__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.notifications__item {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2) var(--gv-space-3);
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container);
}

.notifications__item--unread {
  background: var(--gv-color-primary-container);
  color: var(--gv-color-on-primary-container);
}

.notifications__item-head {
  display: flex;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.notifications__item-title {
  font: var(--gv-type-label-large);
}

.notifications__time {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  white-space: nowrap;
}

.notifications__detail {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}
</style>
