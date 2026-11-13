<script lang="ts">
import type { IconName } from "@/components/icons/registry";

/** One key/value pair of the detail meta grid. */
export interface DetailMetaItem {
  label: string;
  value: string;
  /** Leading icon for the value (ratings use the star glyph). */
  icon?: IconName;
}

/** Breadcrumb leaf pointing back at where the reader came from. */
export interface DetailCrumb {
  label: string;
  to?: string;
}
</script>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import ErrorState from "@/components/ui/ErrorState.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Skeleton from "@/components/ui/Skeleton.vue";
import "@/views/gallery/i18n";

/**
 * Shared skeleton for the local and the online gallery detail pages:
 *
 *   head (back + source crumb + h1 / subtitle)
 *   hero  (cover | category chips + info | meta grid)
 *   actions row (all controls on the same ladder step)
 *   tag groups
 *   thumbnails
 *   extra (page-specific management area)
 *
 * The meta grid never leaves a lone cell on its last row: the desktop column
 * count steps down while `count % columns === 1`, and on the two-column mobile
 * grid the final item spans the full width.
 */
const props = withDefaults(
  defineProps<{
    status?: "loading" | "ready" | "error";
    errorTitle?: string;
    errorBody?: string;
    title: string;
    subtitle?: string;
    titleTestid?: string;
    subtitleTestid?: string;
    crumbs?: DetailCrumb[];
    /** Used when the in-app history has no previous entry. */
    backFallback?: string;
    coverUrl?: string;
    coverAlt?: string;
    coverTestid?: string;
    coverFallbackTestid?: string;
    coverFallbackLabel?: string;
    /** Online covers come from a CDN that must not receive the referrer. */
    coverNoReferrer?: boolean;
    meta?: DetailMetaItem[];
  }>(),
  {
    status: "ready",
    errorTitle: "",
    errorBody: "",
    subtitle: "",
    titleTestid: "detail-title",
    subtitleTestid: "detail-subtitle",
    crumbs: () => [],
    backFallback: "/",
    coverUrl: "",
    coverAlt: "",
    coverTestid: "detail-cover",
    coverFallbackTestid: "detail-cover-fallback",
    coverFallbackLabel: "",
    coverNoReferrer: false,
    meta: () => [],
  },
);

const emit = defineEmits<{ retry: []; back: [] }>();

const { t } = useI18n();
const router = useRouter();

const coverBroken = ref(false);

watch(
  () => props.coverUrl,
  () => {
    coverBroken.value = false;
  },
);

/**
 * Desktop column count: at most four, and never one that leaves a single cell
 * on the last row (5 → 3, 9 → 3, …). Mobile always uses two columns and spans
 * the last item when the count is odd.
 */
const columns = computed(() => {
  const total = props.meta.length;
  if (total <= 1) return 1;
  let value = Math.min(4, total);
  while (value > 2 && total % value === 1) value -= 1;
  return value;
});

const metaWide = computed(() => props.meta.length % 2 === 1);

const metaStyle = computed<Record<string, string>>(() => ({
  "--detail-meta-cols": String(columns.value),
}));

function goBack(): void {
  emit("back");
  const previous = router.options.history.state.back;
  if (previous) router.back();
  else void router.push(props.backFallback);
}
</script>

<template>
  <section
    class="detail"
    data-testid="gallery-detail"
    :aria-busy="status === 'loading' || undefined"
  >
    <div v-if="status === 'loading'" class="detail__loading" data-testid="detail-loading">
      <div class="detail__loading-head">
        <Skeleton variant="line" :lines="2" />
      </div>
      <div class="detail__loading-hero">
        <Skeleton variant="card" class="detail__loading-cover" />
        <div class="detail__loading-info">
          <Skeleton variant="line" :lines="2" />
          <Skeleton variant="line" :lines="2" />
        </div>
      </div>
      <div class="detail__loading-actions">
        <Skeleton variant="line" :lines="1" />
      </div>
    </div>

    <ErrorState
      v-else-if="status === 'error'"
      :title="errorTitle || t('gallery.loadFailed')"
      :body="errorBody"
      :retry-label="t('gallery.retry')"
      testid="detail-error"
      @retry="$emit('retry')"
    />

    <template v-else>
      <header class="detail__head">
        <nav v-if="crumbs.length" class="detail__crumbs" :aria-label="t('gallery.breadcrumb')">
          <template v-for="(crumb, index) in crumbs" :key="`${crumb.label}-${index}`">
            <span v-if="index > 0" class="detail__crumb-sep" aria-hidden="true">/</span>
            <RouterLink v-if="crumb.to" class="detail__crumb" :to="crumb.to">
              {{ crumb.label }}
            </RouterLink>
            <span v-else class="detail__crumb detail__crumb--current">{{ crumb.label }}</span>
          </template>
        </nav>

        <div class="detail__title-row">
          <IconButton
            class="detail__back"
            :label="t('gallery.back')"
            data-testid="detail-back"
            @click="goBack"
          >
            <Icon name="back" size="md" />
          </IconButton>
          <div class="detail__titles">
            <h1 class="detail__title" :data-testid="titleTestid">{{ title }}</h1>
            <p
              v-if="subtitle"
              class="detail__subtitle"
              :data-testid="subtitleTestid"
            >
              {{ subtitle }}
            </p>
          </div>
          <div v-if="$slots['head-actions']" class="detail__head-actions">
            <slot name="head-actions" />
          </div>
        </div>
      </header>

      <article class="detail__hero" data-testid="detail-hero">
        <div class="detail__cover">
          <img
            v-if="coverUrl && !coverBroken"
            class="detail__image"
            :data-testid="coverTestid"
            :src="coverUrl"
            :alt="coverAlt"
            :referrerpolicy="coverNoReferrer ? 'no-referrer' : undefined"
            decoding="async"
            @error="coverBroken = true"
          />
          <div v-else class="detail__cover-fallback" :data-testid="coverFallbackTestid">
            <span>{{ coverFallbackLabel }}</span>
          </div>
        </div>

        <div class="detail__info">
          <div v-if="$slots.badges" class="detail__chips">
            <slot name="badges" />
          </div>
          <slot name="info-extra" />
        </div>

        <dl v-if="meta.length > 1" class="detail__meta" :style="metaStyle" data-testid="detail-meta">
          <div
            v-for="(item, index) in meta"
            :key="item.label"
            class="detail__meta-item"
            :class="{
              'detail__meta-item--wide': metaWide && index === meta.length - 1,
            }"
            data-testid="detail-meta-item"
          >
            <dt>{{ item.label }}</dt>
            <dd>
              <Icon v-if="item.icon" :name="item.icon" size="sm" class="detail__meta-icon" />
              <span>{{ item.value }}</span>
            </dd>
          </div>
        </dl>
        <p v-else-if="meta.length === 1" class="detail__meta-line" data-testid="detail-meta">
          <span class="detail__meta-line-label">{{ meta[0].label }}</span>
          <span>{{ meta[0].value }}</span>
        </p>
      </article>

      <div v-if="$slots.actions || $slots.secondary" class="detail__action-block">
        <div
          v-if="$slots.actions"
          class="detail__actions"
          data-gv-toolbar="detail-actions"
          data-testid="detail-actions"
        >
          <slot name="actions" />
        </div>

        <div v-if="$slots.secondary" class="detail__secondary" data-testid="detail-secondary">
          <slot name="secondary" />
        </div>
      </div>

      <div v-if="$slots.tags" class="detail__section detail__tags">
        <slot name="tags" />
      </div>

      <div v-if="$slots.thumbs" class="detail__section detail__thumbs">
        <slot name="thumbs" />
      </div>

      <div v-if="$slots.extra" class="detail__extra">
        <slot name="extra" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-5);
  min-width: 0;
}

.detail__loading {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.detail__loading-hero {
  display: grid;
  grid-template-columns: 176px minmax(0, 1fr);
  gap: var(--gv-space-4);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
}

.detail__loading-info {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.detail__loading-actions {
  max-width: 320px;
}

.detail__head {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.detail__crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.detail__crumb {
  color: var(--gv-color-on-surface-variant);
  text-decoration: none;
}

.detail__crumb:hover {
  color: var(--gv-color-primary-text);
}

.detail__crumb--current {
  color: var(--gv-color-on-surface);
}

.detail__crumb-sep {
  color: var(--gv-color-outline);
}

.detail__title-row {
  display: flex;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.detail__titles {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.detail__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-headline-small);
  overflow-wrap: anywhere;
}

.detail__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-medium);
  overflow-wrap: anywhere;
}

.detail__head-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--gv-space-2);
  margin-inline-start: auto;
}

.detail__hero {
  display: grid;
  grid-template-columns: 176px minmax(0, 1fr);
  grid-template-areas:
    "cover info"
    "cover meta";
  gap: var(--gv-space-2) var(--gv-space-4);
  align-items: start;
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container);
  box-shadow: var(--gv-elev-1);
}

.detail__cover {
  grid-area: cover;
  width: 176px;
}

.detail__image,
.detail__cover-fallback {
  display: block;
  width: 100%;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container-highest);
}

.detail__image {
  object-fit: cover;
}

.detail__cover-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
  text-align: center;
}

.detail__info {
  grid-area: info;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.detail__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

.detail__meta {
  grid-area: meta;
  display: grid;
  grid-template-columns: repeat(var(--detail-meta-cols, 4), minmax(0, 1fr));
  gap: var(--gv-space-3) var(--gv-space-4);
  margin: 0;
  min-width: 0;
}

.detail__meta-item {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
}

.detail__meta-item dt {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-medium);
}

.detail__meta-item dd {
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-medium);
  overflow-wrap: anywhere;
}

.detail__meta-icon {
  color: var(--gv-color-on-surface-variant);
}

.detail__meta-line {
  grid-area: meta;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--gv-space-2);
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
}

.detail__meta-line-label {
  color: var(--gv-color-on-surface-variant);
}

.detail__action-block {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  min-width: 0;
}

.detail__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.detail__section {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  min-width: 0;
}

.detail__secondary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
  min-width: 0;
}

.detail__extra {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  min-width: 0;
}

/* Two tag-group columns keep the 1280 layout from turning into six short rows
   (OD-09); the group internals stay owned by TagGroups. */
@media (min-width: 840px) {
  .detail__tags :deep(.tag-groups) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--gv-space-4);
    align-items: start;
  }

  .detail__tags :deep(.tag-groups__empty) {
    grid-column: 1 / -1;
  }
}

/* --gv-bp-compact = 600px */
@media (max-width: 599.98px) {
  .detail {
    gap: var(--gv-space-4);
  }

  .detail__loading-hero,
  .detail__hero {
    grid-template-columns: 104px minmax(0, 1fr);
    grid-template-areas:
      "cover info"
      "meta meta";
    padding: var(--gv-space-3);
  }

  .detail__cover {
    width: 104px;
  }

  .detail__meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail__meta-item--wide {
    grid-column: 1 / -1;
  }

  .detail__title-row {
    align-items: flex-start;
  }

  .detail__actions {
    gap: var(--gv-space-2);
  }
}
</style>
