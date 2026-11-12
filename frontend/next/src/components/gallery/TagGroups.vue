<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { GalleryTag } from "@/api/gallery";

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
  }>(),
  { tags: () => [] },
);

const emit = defineEmits<{ select: [tag: GalleryTag] }>();
const { t, te, locale } = useI18n();

function tagText(tag: GalleryTag): string {
  if (locale.value.startsWith("zh") && tag.display) return tag.display;
  return tag.name;
}

function namespaceLabel(namespace: string): string {
  const key = `gallery.namespaces.${namespace}`;
  return te(key) ? t(key) : namespace;
}

const groups = computed<TagGroupItem[]>(() => {
  const byNamespace = new Map<string, Map<string, GalleryTag>>();
  for (const tag of props.tags ?? []) {
    const namespace = tag.namespace || "misc";
    let bucket = byNamespace.get(namespace);
    if (!bucket) {
      bucket = new Map<string, GalleryTag>();
      byNamespace.set(namespace, bucket);
    }
    if (!bucket.has(tag.name)) bucket.set(tag.name, tag);
  }

  return [...byNamespace.entries()]
    .map(([namespace, bucket]) => ({
      namespace,
      tags: [...bucket.values()].sort((a, b) =>
        tagText(a).localeCompare(tagText(b), locale.value, { sensitivity: "base" }),
      ),
    }))
    .sort(
      (a, b) =>
        namespaceRank(a.namespace) - namespaceRank(b.namespace) ||
        a.namespace.localeCompare(b.namespace),
    );
});
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
      <h3 class="tag-group__title">{{ namespaceLabel(group.namespace) }}</h3>
      <ul class="tag-group__list">
        <li v-for="tag in group.tags" :key="`${tag.namespace}:${tag.name}`">
          <button
            type="button"
            class="tag-chip"
            data-testid="tag-chip"
            @click="emit('select', tag)"
          >
            <span class="tag-chip__namespace">{{ tag.namespace }}:</span>
            <span class="tag-chip__name">{{ tagText(tag) }}</span>
          </button>
        </li>
      </ul>
    </div>

    <p v-if="groups.length === 0" class="tag-groups__empty" data-testid="tag-empty">
      {{ t("gallery.noTags") }}
    </p>
  </div>
</template>

<style scoped>
.tag-groups {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
}

.tag-group__title {
  margin: 0 0 var(--gv-space-1);
  font: var(--gv-type-label-large);
  color: var(--gv-color-primary-text);
}

.tag-group__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  height: 24px;
  padding: 0 var(--gv-space-2);
  border: 1px solid transparent;
  border-radius: var(--gv-radius-xs);
  background: var(--gv-color-surface-variant);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
  cursor: pointer;
  transition:
    background-color var(--gv-motion-duration-short) var(--gv-motion-ease-standard),
    color var(--gv-motion-duration-short) var(--gv-motion-ease-standard);
}

.tag-chip__namespace {
  font-weight: 600;
  color: var(--gv-color-on-surface);
}

.tag-chip__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-chip:hover {
  background: var(--gv-color-surface-container-highest);
}

.tag-chip:focus-visible {
  outline: var(--gv-state-focus-ring-width) solid var(--gv-color-focus-ring);
  outline-offset: var(--gv-state-focus-ring-offset);
}

.tag-groups__empty {
  margin: 0;
  font: var(--gv-type-body-small);
  color: var(--gv-color-on-surface-variant);
}
</style>
