<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import type { SeriesMember } from "@/api/series";

const props = defineProps<{
  member: SeriesMember;
  selected: boolean;
}>();

const emit = defineEmits<{ toggle: [member: SeriesMember, checked: boolean] }>();

const { t } = useI18n();

const title = computed(() => props.member.title || `gid ${props.member.gid ?? ""}`);
const isLocal = computed(() => Boolean(props.member.is_local));
const pages = computed(() => props.member.page_count ?? 0);
const tags = computed(() => (props.member.tags ?? []).slice(0, 4));
const galleryLink = computed(() =>
  isLocal.value && props.member.gallery_id
    ? { name: "gallery" as const, params: { id: props.member.gallery_id } }
    : null,
);
const externalLink = computed(() => {
  if (isLocal.value) return "";
  const value = props.member.url ?? "";
  return /^https?:\/\//i.test(value) ? value : "";
});

function onToggle(event: Event): void {
  emit("toggle", props.member, (event.target as HTMLInputElement).checked);
}
</script>

<template>
  <article
    class="member"
    :class="{ 'member--selected': selected }"
    data-testid="series-member"
    :data-local="isLocal ? '1' : '0'"
  >
    <label class="member__check" :title="t('seriesPage.selectMember', { title })">
      <input
        type="checkbox"
        :checked="selected"
        :aria-label="t('seriesPage.selectMember', { title })"
        @change="onToggle"
      />
    </label>

    <RouterLink
      v-if="galleryLink"
      class="member__cover"
      :to="galleryLink"
      :title="title"
    >
      <img
        v-if="member.cover_url"
        class="member__image"
        :src="member.cover_url"
        :alt="title"
        loading="lazy"
        decoding="async"
      />
      <span v-else class="member__placeholder">{{ t("seriesPage.noCover") }}</span>
      <span class="member__state" :data-local="isLocal ? '1' : '0'">
        {{ isLocal ? t("seriesPage.localBadge") : t("seriesPage.cloudBadge") }}
      </span>
    </RouterLink>
    <a
      v-else-if="externalLink"
      class="member__cover"
      :href="externalLink"
      target="_blank"
      rel="noopener noreferrer"
      :title="title"
    >
      <img
        v-if="member.cover_url"
        class="member__image"
        :src="member.cover_url"
        :alt="title"
        loading="lazy"
        decoding="async"
      />
      <span v-else class="member__placeholder">{{ t("seriesPage.noCover") }}</span>
      <span class="member__state" :data-local="isLocal ? '1' : '0'">
        {{ isLocal ? t("seriesPage.localBadge") : t("seriesPage.cloudBadge") }}
      </span>
    </a>
    <div v-else class="member__cover">
      <img
        v-if="member.cover_url"
        class="member__image"
        :src="member.cover_url"
        :alt="title"
        loading="lazy"
        decoding="async"
      />
      <span v-else class="member__placeholder">{{ t("seriesPage.noCover") }}</span>
      <span class="member__state" :data-local="isLocal ? '1' : '0'">
        {{ isLocal ? t("seriesPage.localBadge") : t("seriesPage.cloudBadge") }}
      </span>
    </div>

    <p class="member__title" :title="title">{{ title }}</p>
    <div class="member__meta">
      <span v-if="pages">{{ pages }}P</span>
      <span v-if="member.category">{{ member.category }}</span>
    </div>
    <div v-if="tags.length" class="member__tags">
      <RouterLink
        v-for="tag in tags"
        :key="`${tag.namespace}:${tag.name}`"
        class="member__tag"
        :to="{ name: 'library', query: { tags: `${tag.namespace}:${tag.name}` } }"
        :title="t('seriesPage.filterTags')"
      >
        {{ tag.display || tag.name }}
      </RouterLink>
    </div>
  </article>
</template>

<style scoped>
.member {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
  min-width: 0;
  padding: var(--gv-space-2);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.member--selected {
  border-color: var(--gv-color-primary);
  box-shadow: var(--gv-elev-1);
}

.member__check {
  position: absolute;
  top: var(--gv-space-2);
  right: var(--gv-space-2);
  z-index: 5;
  scroll-margin-top: calc(var(--gv-size-topbar) + var(--gv-space-4));
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-touch);
  height: var(--gv-size-touch);
  border-radius: var(--gv-radius-full);
  background: var(--gv-color-surface-container-highest);
  box-shadow: var(--gv-elev-1);
  cursor: pointer;
}

.member__check input {
  width: 20px;
  height: 20px;
  accent-color: var(--gv-color-primary);
  cursor: pointer;
}

.member__cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: var(--gv-size-card-cover-aspect);
  overflow: hidden;
  border-radius: var(--gv-radius-sm);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface-variant);
  text-decoration: none;
}

.member__image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.member__placeholder {
  font: var(--gv-type-label-small);
}

.member__state {
  position: absolute;
  top: var(--gv-space-1);
  left: var(--gv-space-1);
  height: 20px;
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  line-height: 20px;
}

.member__state[data-local="1"] {
  background: var(--gv-color-success-container);
  color: var(--gv-color-on-success-container);
}

.member__title {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-body-small);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.member__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.member__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

.member__tag {
  height: 20px;
  padding: 0 var(--gv-space-1);
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  line-height: 20px;
  text-decoration: none;
}

.member__tag:hover {
  background: var(--gv-color-surface-container-highest);
  color: var(--gv-color-on-surface);
}
</style>
