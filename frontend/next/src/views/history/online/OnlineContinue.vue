<script setup lang="ts">
/**
 * "Continue reading online" strip for the home page.
 *
 * Data comes from `GET /api/eh/history` (online progress only; the backend
 * never stores resolved image URLs). Rendered as a self-contained section so
 * the home view can drop it in without owning any state; the route table and
 * the home view are outside this batch's scope.
 */
import { onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import Skeleton from "@/components/ui/Skeleton.vue";
import { fetchOnlineHistory, type OnlineHistoryItem } from "@/api/eh-reader";
import { useOnlineReaderI18n } from "@/views/online/reader/i18n";

const { tr } = useOnlineReaderI18n();

const items = ref<OnlineHistoryItem[]>([]);
const loading = ref(true);
const failed = ref(false);
let controller: AbortController | null = null;

async function load(): Promise<void> {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  failed.value = false;
  try {
    const data = await fetchOnlineHistory(1, 8, { signal: controller.signal });
    items.value = data.items;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    items.value = [];
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

function titleFor(item: OnlineHistoryItem): string {
  return item.title || `#${item.gid}`;
}

function progressFor(item: OnlineHistoryItem): string {
  if (item.total_pages && item.total_pages > 0) {
    return tr("continue.pageOf", { page: item.page, total: item.total_pages });
  }
  return tr("continue.unknownTotal", { page: item.page });
}

function targetFor(item: OnlineHistoryItem) {
  return {
    name: "online-reader",
    params: {
      gid: item.gid,
      token: item.token,
      page: Math.max(0, item.page - 1),
    },
  };
}

onMounted(() => {
  void load();
});

onBeforeUnmount(() => {
  controller?.abort();
});
</script>

<template>
  <section
    v-if="loading || items.length > 0"
    class="online-continue"
    data-testid="online-continue"
    :data-loading="loading ? '1' : '0'"
    :data-count="items.length"
  >
    <header class="online-continue__header">
      <h2 class="online-continue__title">{{ tr("continue.title") }}</h2>
      <p class="online-continue__subtitle">{{ tr("continue.subtitle") }}</p>
    </header>

    <div v-if="loading" class="online-continue__row" data-testid="online-continue-loading">
      <div
        v-for="n in 3"
        :key="n"
        class="online-continue__card online-continue__card--skeleton"
        aria-hidden="true"
      >
        <Skeleton variant="list" />
      </div>
    </div>

    <p v-else-if="failed" class="online-continue__note">{{ tr("continue.empty") }}</p>

    <ul v-else class="online-continue__row">
      <li v-for="item in items" :key="`${item.gid}:${item.token}`" class="online-continue__item">
        <RouterLink
          class="online-continue__card"
          data-testid="online-continue-item"
          :to="targetFor(item)"
        >
          <img
            v-if="item.thumb"
            class="online-continue__thumb"
            :src="item.thumb"
            :alt="titleFor(item)"
            referrerpolicy="no-referrer"
            loading="lazy"
            decoding="async"
          />
          <span v-else class="online-continue__thumb online-continue__thumb--empty" aria-hidden="true" />
          <span class="online-continue__text">
            <span class="online-continue__name" :title="titleFor(item)">{{ titleFor(item) }}</span>
            <span class="online-continue__progress" data-testid="online-continue-progress">
              {{ progressFor(item) }}
            </span>
          </span>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.online-continue {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  width: 100%;
}

.online-continue__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.online-continue__title {
  margin: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
}

.online-continue__subtitle {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}

.online-continue__row {
  display: flex;
  gap: var(--gv-space-3);
  margin: 0;
  padding: 0 0 var(--gv-space-1);
  list-style: none;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-width: thin;
}

.online-continue__item {
  flex: 0 0 auto;
}

.online-continue__card {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  width: 260px;
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
  color: inherit;
  text-decoration: none;
  transition: background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.online-continue__card:hover {
  background: var(--gv-color-surface-container);
}

.online-continue__card:focus-visible {
  outline: 2px solid var(--gv-color-focus-ring);
  outline-offset: 2px;
}

.online-continue__card--skeleton {
  cursor: default;
}

.online-continue__thumb {
  flex: 0 0 auto;
  width: 54px;
  height: 72px;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
  object-fit: cover;
}

.online-continue__thumb--empty {
  display: block;
}

.online-continue__text {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.online-continue__name {
  display: -webkit-box;
  overflow: hidden;
  font: var(--gv-type-body-medium);
  color: var(--gv-color-on-surface);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.online-continue__progress {
  font: var(--gv-type-label-small);
  color: var(--gv-color-primary-text);
}

.online-continue__note {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}
</style>
