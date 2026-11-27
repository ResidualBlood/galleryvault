<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { GalleryTag } from "@/api/gallery";
import TagChip from "@/components/tags/TagChip.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import {
  namespaceLabel,
  tagKey,
  tagLabel,
  tagNamespace,
  type TagMenuEvent,
} from "@/components/tags/tag-utils";
import type { TagSource } from "@/components/tags/useTagNavigation";
import "@/components/tags/i18n";

/** Canonical detail-page namespace order (legacy gallery view, then extras). */
const NAMESPACE_ORDER = [
  "parody",
  "character",
  "group",
  "artist",
  "language",
  "location",
  "category",
  "female",
  "male",
  "mixed",
  "misc",
  "other",
  "cosplayer",
  "reclass",
  "temp",
  "local",
] as const;

const UPLOADER_RANK = 10_000;
const UNKNOWN_RANK = 1_000;

function namespaceRank(namespace: string): number {
  if (namespace === "uploader") return UPLOADER_RANK;
  const index = (NAMESPACE_ORDER as readonly string[]).indexOf(namespace);
  return index === -1 ? UNKNOWN_RANK : index;
}

interface TagGroupItem {
  namespace: string;
  tags: GalleryTag[];
}

const props = withDefaults(
  defineProps<{
    tags?: GalleryTag[];
    source?: TagSource;
  }>(),
  { tags: () => [], source: "local" },
);

const emit = defineEmits<{ select: [tag: GalleryTag] }>();
const { t, te, locale } = useI18n();

const menu = ref<TagMenuEvent | null>(null);

function namespaceTitle(namespace: string): string {
  return namespaceLabel(namespace, t);
}

const groups = computed<TagGroupItem[]>(() => {
  const byNamespace = new Map<string, Map<string, GalleryTag>>();
  for (const tag of props.tags ?? []) {
    const namespace = tagNamespace(tag);
    // DESIGN C07: a namespace without an i18n title is not rendered at all
    // (no raw key fallback in group headings).
    if (!te(`gallery.namespaces.${namespace}`)) continue;
    let bucket = byNamespace.get(namespace);
    if (!bucket) {
      bucket = new Map<string, GalleryTag>();
      byNamespace.set(namespace, bucket);
    }
    const key = tagKey(tag);
    if (!bucket.has(key)) bucket.set(key, tag);
  }

  return [...byNamespace.entries()]
    .map(([namespace, bucket]) => ({
      namespace,
      tags: [...bucket.values()].sort((a, b) =>
        tagLabel(a, locale.value).localeCompare(tagLabel(b, locale.value), locale.value, {
          sensitivity: "base",
        }),
      ),
    }))
    .sort(
      (a, b) =>
        namespaceRank(a.namespace) - namespaceRank(b.namespace) ||
        a.namespace.localeCompare(b.namespace),
    );
});

function onMenu(event: TagMenuEvent): void {
  menu.value = event;
}
</script>

<template>
  <div class="tag-groups" data-testid="tag-groups">
    <div
      v-for="group in groups"
      :key="group.namespace"
      class="tag-group"
      data-testid="tag-group"
      :data-ns="group.namespace"
    >
      <h3 class="tag-group__heading">
        <span class="tag-group__title">{{ namespaceTitle(group.namespace) }}</span>
        <span class="tag-group__count">{{ group.tags.length }}</span>
      </h3>
      <ul class="tag-group__list">
        <li v-for="tag in group.tags" :key="tagKey(tag)">
          <TagChip
            :tag="tag"
            :size="28"
            data-testid="tag-chip"
            @select="emit('select', tag)"
            @menu="onMenu"
          />
        </li>
      </ul>
    </div>

    <p v-if="groups.length === 0" class="tag-groups__empty" data-testid="tag-empty">
      {{ t("gallery.noTags") }}
    </p>

    <TagMenu
      v-if="menu"
      :tag="menu.tag"
      :x="menu.x"
      :y="menu.y"
      :source="source"
      @close="menu = null"
    />
  </div>
</template>

<style scoped>
.tag-groups {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.tag-group__heading {
  display: flex;
  align-items: baseline;
  gap: var(--gv-space-2);
  margin: 0 0 var(--gv-space-1);
}

.tag-group__title {
  font: var(--gv-type-label-large);
  color: var(--gv-color-primary-text);
}

.tag-group__count {
  font: var(--gv-type-label-small);
  color: var(--gv-color-on-surface-variant);
}

.tag-group__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.tag-groups__empty {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}
</style>
