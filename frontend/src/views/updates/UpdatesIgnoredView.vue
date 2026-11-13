<!-- gv-polish:pending -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import {
  fetchIgnoredUpdates,
  unignoreUpdates,
  type GalleryUpdate,
} from "@/api/updates";
import { useUiStore } from "@/stores/ui";
import { galleryThumbUrl } from "@/views/updates/url";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import { ensureMaintenanceMessages } from "@/views/updates/i18n";

ensureMaintenanceMessages();

const ui = useUiStore();
const { t } = useI18n();

const items = ref<GalleryUpdate[]>([]);
const selected = ref<number[]>([]);
const loading = ref(true);
const error = ref("");

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchIgnoredUpdates();
    items.value = data.items ?? [];
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

function toggle(id: number): void {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id];
}

async function unignore(ids: number[]): Promise<void> {
  if (!ids.length) {
    ui.error(t("maintenance.updates.message.selectedRequired"));
    return;
  }
  try {
    await unignoreUpdates(ids);
    ui.success(t("maintenance.updates.ignored.unignored", { n: ids.length }));
    selected.value = [];
    await load();
  } catch (cause) {
    ui.error(cause instanceof Error ? cause.message : String(cause));
  }
}

onMounted(load);
</script>

<template>
  <section class="ignored" data-testid="updates-ignored-view">
    <header class="ignored__header">
      <p class="ignored__eyebrow">{{ t("maintenance.updates.eyebrow") }}</p>
      <h1 class="ignored__title">{{ t("maintenance.updates.ignored.title") }}</h1>
      <p class="ignored__subtitle">{{ t("maintenance.updates.ignored.subtitle") }}</p>
    </header>

    <div class="ignored__toolbar">
      <Button
        data-testid="updates-unignore-selected"
        :disabled="!selected.length"
        @click="unignore(selected)"
      >
        {{ t("maintenance.updates.ignored.unignoreSelected") }}
      </Button>
      <RouterLink class="ignored__link" :to="{ name: 'updates' }">
        {{ t("maintenance.updates.title") }}
      </RouterLink>
    </div>

    <div v-if="loading" class="ignored__skeletons" aria-hidden="true">
      <Skeleton v-for="index in 4" :key="index" variant="list" />
    </div>

    <ErrorState
      v-else-if="error"
      :title="t('common.errorTitle')"
      :body="error"
      :retry-label="t('maintenance.shared.retry')"
      @retry="load"
    />

    <EmptyState
      v-else-if="!items.length"
      :title="t('maintenance.updates.ignored.empty')"
      testid="updates-ignored-empty"
    />

    <ul v-else class="ignored__list">
      <li
        v-for="item in items"
        :key="item.id"
        class="ignored__item"
        :data-testid="`updates-ignored-${item.id}`"
      >
        <label class="ignored__check">
          <input
            type="checkbox"
            :checked="selected.includes(item.id)"
            :aria-label="t('maintenance.shared.select')"
            @change="toggle(item.id)"
          />
          <GalleryThumb :src="item.cover_url || galleryThumbUrl(item.gallery_id)" :alt="item.title" />
          <span class="ignored__body">
            <RouterLink
              class="ignored__gallery"
              :to="{ name: 'gallery', params: { id: item.gallery_id } }"
            >
              {{ item.title }}
            </RouterLink>
            <span class="ignored__gid">
              {{ item.old_gid }} {{ t("maintenance.updates.toNewer") }} {{ item.new_gid }}
            </span>
          </span>
        </label>
        <Button
          variant="outlined"
          size="compact"
          data-testid="updates-unignore-one"
          @click="unignore([item.id])"
        >
          {{ t("maintenance.updates.ignored.unignore") }}
        </Button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.ignored {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  max-width: var(--gv-size-content-max);
  margin: 0 auto;
}

.ignored__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.ignored__eyebrow {
  margin: 0;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
  letter-spacing: var(--gv-type-label-small-tracking);
}

.ignored__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
}

.ignored__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.ignored__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.ignored__link {
  margin-left: auto;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.ignored__skeletons,
.ignored__list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ignored__item {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  padding: var(--gv-space-2) var(--gv-space-3);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.ignored__check {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--gv-space-3);
  min-width: 0;
}

.ignored__body {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.ignored__gallery {
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ignored__gid {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

@media (max-width: 599px) {
  .ignored__item {
    align-items: flex-start;
    flex-direction: column;
  }

  .ignored__link {
    margin-left: 0;
  }
}
</style>
