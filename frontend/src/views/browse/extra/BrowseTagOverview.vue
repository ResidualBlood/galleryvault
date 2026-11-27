<script setup lang="ts">
/**
 * Tag namespace overview shown after the recently-added list.
 *
 * Audit BR-05 / BR-06: the section link reads "View all" (not a second "Tags"),
 * namespaces always use `gallery.namespaces.*` (no raw `uploader` / `reclass`
 * leaking into a Chinese UI), untranslated namespaces are hidden, and the head
 * uses the same right-aligned `label-large` link as every other section.
 */
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import { fetchTagFacets } from "@/api/library";
import "@/components/tags/i18n";

const { t, te } = useI18n();

const facets = ref<Array<{ namespace: string; total: number }>>([]);
const loading = ref(true);

const pills = computed(() => {
  const counts = [...facets.value].sort((a, b) => b.total - a.total);
  return counts
    .filter((facet) => te(`gallery.namespaces.${facet.namespace}`))
    .map((facet) => ({
      namespace: facet.namespace,
      total: facet.total,
      label: t(`gallery.namespaces.${facet.namespace}`),
    }));
});

onMounted(async () => {
  try {
    const data = await fetchTagFacets();
    facets.value = (data.facets ?? []).filter((facet) => Boolean(facet.namespace));
  } catch {
    facets.value = [];
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <section class="overview" data-testid="browse-tag-overview">
    <div class="overview__head">
      <h2 class="overview__title">{{ t("legacy.tags") }}</h2>
      <RouterLink class="overview__link" :to="{ name: 'tags' }">
        <span>{{ t("library.home.viewAllTags") }}</span>
        <Icon name="chevron-right" size="sm" aria-hidden="true" />
      </RouterLink>
    </div>
    <div v-if="loading" class="overview__skeleton" aria-hidden="true">
      <Skeleton variant="line" :lines="1" />
    </div>
    <p v-else-if="!pills.length" class="overview__empty">{{ t("legacy.noData") }}</p>
    <div v-else class="overview__pills">
      <RouterLink
        v-for="pill in pills"
        :key="pill.namespace"
        class="overview__pill"
        :data-testid="`browse-ns-${pill.namespace}`"
        :aria-label="t('library.home.tagCount', { count: pill.total })"
        :title="t('library.home.tagCount', { count: pill.total })"
        :to="{ name: 'tags', query: { ns: pill.namespace } }"
      >
        {{ pill.label }} <b>{{ pill.total }}</b>
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
}

.overview__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

.overview__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-medium);
}

.overview__link {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.overview__link:hover {
  text-decoration: underline;
}

.overview__pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
}

.overview__pill {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: 32px;
  padding: 0 var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
  text-decoration: none;
}

.overview__pill:hover {
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface);
}

.overview__pill b {
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-small);
}

.overview__empty {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.overview__skeleton {
  max-width: 320px;
}
</style>
