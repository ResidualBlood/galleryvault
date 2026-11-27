<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import Checkbox from "@/components/ui/Checkbox.vue";
import EmptyState from "@/components/ui/EmptyState.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import PageHeader from "@/components/ui/PageHeader.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import Toolbar from "@/components/ui/Toolbar.vue";
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

const router = useRouter();
const ui = useUiStore();
const { t } = useI18n();

const items = ref<GalleryUpdate[]>([]);
const selected = ref<number[]>([]);
const loading = ref(true);
const error = ref("");

const allSelected = computed(
  () => items.value.length > 0 && selected.value.length === items.value.length,
);
const partialSelection = computed(
  () => selected.value.length > 0 && !allSelected.value,
);

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

function toggleAll(): void {
  selected.value = allSelected.value ? [] : items.value.map((item) => item.id);
}

function back(): void {
  void router.push({ name: "updates" });
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
    <PageHeader
      :title="t('maintenance.updates.ignored.title')"
      :count="items.length"
      back
      :back-label="t('maintenance.updates.ignored.back')"
      testid="updates-ignored-header"
      @back="back"
    />

    <Toolbar class="ignored__toolbar" size="lg" testid="updates-ignored-toolbar">
      <Button
        variant="tonal"
        icon="status-blocked"
        data-testid="updates-unignore-selected"
        :disabled="!selected.length"
        @click="unignore(selected)"
      >
        {{ t("maintenance.updates.ignored.unignoreSelected") }}
      </Button>
    </Toolbar>
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
      icon="updates"
      :title="t('maintenance.updates.ignored.empty')"
      :body="t('maintenance.updates.ignored.emptyBody')"
      :action-label="t('maintenance.updates.ignored.back')"
      testid="updates-ignored-empty"
      @action="back"
    />

    <template v-else>
      <div class="ignored__listbar">
        <Checkbox
          :model-value="allSelected"
          :indeterminate="partialSelection"
          :label="t('maintenance.shared.selectAll')"
          data-testid="updates-ignored-select-all"
          @change="toggleAll"
        />
        <span class="ignored__count">
          {{ t("maintenance.updates.ignored.count", { n: items.length }) }}
        </span>
      </div>

      <ul class="ignored__list">
        <li
          v-for="item in items"
          :key="item.id"
          class="ignored__item"
          :class="{ 'ignored__item--selected': selected.includes(item.id) }"
          :data-testid="`updates-ignored-${item.id}`"
        >
          <Checkbox
            :model-value="selected.includes(item.id)"
            :aria-label="t('maintenance.shared.select')"
            role="checkbox"
            :aria-checked="selected.includes(item.id)"
            :data-testid="`updates-ignored-select-${item.id}`"
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
              {{ item.old_gid }}
              <Icon name="forward" size="dense" aria-hidden="true" />
              <span class="sr-only">{{ t("maintenance.updates.toNewer") }}</span>
              {{ item.new_gid }}
            </span>
          </span>
          <Button
            variant="outlined"
            size="sm"
            icon="retry"
            data-testid="updates-unignore-one"
            @click="unignore([item.id])"
          >
            {{ t("maintenance.updates.ignored.unignore") }}
          </Button>
        </li>
      </ul>
    </template>
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

.ignored__skeletons,
.ignored__list {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ignored__listbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-3);
  min-height: var(--gv-size-control-lg);
}

.ignored__count {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
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

.ignored__item--selected {
  background: var(--gv-color-secondary-container);
}

.ignored__body {
  display: flex;
  flex: 1;
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

.ignored__gallery:hover {
  color: var(--gv-color-primary-text);
}

.ignored__gid {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.ignored__gid .gv-icon {
  display: inline-block;
  margin: 0 var(--gv-space-1);
  vertical-align: middle;
}

@media (max-width: 599.98px) {
  .ignored__item {
    flex-wrap: wrap;
    align-items: center;
  }

  .ignored__body {
    flex-basis: calc(100% - var(--gv-size-touch) - 56px - var(--gv-space-6));
  }

  .ignored__item > .btn {
    margin-inline-start: auto;
  }
}
</style>
