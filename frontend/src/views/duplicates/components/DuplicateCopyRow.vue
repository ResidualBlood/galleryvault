<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import GalleryThumb from "@/views/updates/components/GalleryThumb.vue";
import Icon from "@/components/icons/Icon.vue";
import TagList from "@/components/tags/TagList.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import { useTagNavigation } from "@/components/tags/useTagNavigation";
import type { TagLike, TagMenuEvent } from "@/components/tags/tag-utils";
import { safeHref } from "@/views/updates/url";

/**
 * One copy row shared by all four duplicate views: thumbnail + title +
 * metadata + tag row + trailing actions. Compact keeps the row horizontal and
 * clamps the title to two lines instead of stacking the thumbnail above the
 * body (DP-06). Tags come from the list payload (no extra request) and use the
 * shared 24px `TagList` (DP-07); long-press / right-click opens the shared tag
 * menu with "copy original".
 */
const props = withDefaults(
  defineProps<{
    title: string;
    thumb?: string | null;
    tags?: TagLike[];
    to?: RouteLocationRaw | null;
    href?: string | null;
    linkTestid?: string;
    testid?: string;
  }>(),
  {
    thumb: "",
    tags: () => [],
    to: null,
    href: null,
    linkTestid: "",
    testid: "",
  },
);

const tagNav = useTagNavigation("local");
const menu = ref<TagMenuEvent | null>(null);

const href = computed(() => (props.href ? safeHref(props.href) : ""));
const linkTag = computed(() => {
  if (props.to) return RouterLink;
  if (href.value) return "a";
  return "span";
});
</script>

<template>
  <div class="dup-copy" :data-testid="testid || undefined">
    <div v-if="$slots.leading" class="dup-copy__leading"><slot name="leading" /></div>
    <GalleryThumb :src="thumb" :alt="title" />
    <div class="dup-copy__body">
      <component
        :is="linkTag"
        class="dup-copy__title"
        :to="to ?? undefined"
        :href="to ? undefined : href || undefined"
        :target="!to && href ? '_blank' : undefined"
        :rel="!to && href ? 'noopener' : undefined"
        :data-testid="linkTestid || undefined"
      >
        <span class="dup-copy__title-text">{{ title }}</span>
        <Icon v-if="!to && href" name="external-link" size="sm" />
      </component>
      <div v-if="$slots.meta" class="dup-copy__meta"><slot name="meta" /></div>
      <TagList
        v-if="tags.length"
        class="dup-copy__tags"
        :tags="tags"
        :max="4"
        :size="24"
        source="local"
        @select="tagNav.navigate($event)"
        @exclude="tagNav.navigate($event, { exclude: true })"
        @menu="menu = $event"
      />
      <div v-if="$slots.actions" class="dup-copy__actions"><slot name="actions" /></div>
    </div>
    <TagMenu v-if="menu" :tag="menu.tag" :x="menu.x" :y="menu.y" @close="menu = null" />
  </div>
</template>

<style scoped>
.dup-copy {
  display: flex;
  align-items: flex-start;
  gap: var(--gv-space-3);
  padding-top: var(--gv-space-3);
}

.dup-copy__leading {
  display: flex;
  flex: none;
  align-items: center;
  align-self: center;
}

.dup-copy__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.dup-copy__title {
  display: inline-flex;
  align-items: center;
  gap: var(--gv-space-1);
  min-width: 0;
  overflow: hidden;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
  text-decoration: none;
}

.dup-copy__title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dup-copy__title:hover {
  color: var(--gv-color-primary-text);
}

.dup-copy__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-1);
}

.dup-copy__tags {
  min-width: 0;
}

.dup-copy__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gv-space-2);
}

@media (max-width: 599.98px) {
  .dup-copy__title-text {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    white-space: normal;
  }
}
</style>
