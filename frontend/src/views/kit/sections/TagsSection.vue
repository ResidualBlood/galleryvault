<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import TagChip from "@/components/tags/TagChip.vue";
import TagList from "@/components/tags/TagList.vue";
import TagMenu from "@/components/tags/TagMenu.vue";
import { useTagNavigation } from "@/components/tags/useTagNavigation";
import {
  tagKey,
  tagRawText,
  type TagLike,
  type TagMenuEvent,
} from "@/components/tags/tag-utils";
import "@/components/tags/i18n";

/**
 * Tag specimen: chip sizes, truncation with `+N`, language switching without a
 * request, click containment inside a link, and the long-press / right-click
 * menu. Data is static so the kit never touches the backend.
 */
const allTags: TagLike[] = [
  { namespace: "female", name: "big breasts", display: "巨乳" },
  { namespace: "male", name: "sole male", display: "单男" },
  { namespace: "mixed", name: "group sex", display: "群交" },
  { namespace: "character", name: "hatsune miku", display: "初音未来" },
  { namespace: "parody", name: "vocaloid", display: "VOCALOID" },
  { namespace: "artist", name: "sample artist", display: "示例作者" },
  { namespace: "group", name: "sample circle", display: "示例社团" },
  { namespace: "cosplayer", name: "sample cosplayer", display: "示例 Coser" },
  { namespace: "language", name: "chinese", display: "中文" },
  { namespace: "other", name: "full color", display: "全彩" },
  { namespace: "reclass", name: "sample reclass", display: "重分类示例" },
  { namespace: "temp", name: "sample temp", display: "临时示例" },
];

const namespaces = [
  "female",
  "male",
  "mixed",
  "artist",
  "group",
  "character",
  "parody",
  "language",
  "cosplayer",
  "other",
  "reclass",
  "location",
  "temp",
  "local",
  "uploader",
] as const;

const namespaceTags: TagLike[] = namespaces.map((namespace, index) => ({
  namespace,
  name: namespace,
  display: `示例 ${index + 1}`,
}));

const returnedTags = allTags.slice(0, 4);
const fullTags = allTags.slice(0, 8);
const showcaseTag = allTags[0];
const linkTag = allTags[3];
const menu = ref<TagMenuEvent | null>(null);
const local = useTagNavigation("local");

function openMenu(event: TagMenuEvent): void {
  menu.value = event;
}

function navigateLocal(tag: TagLike): void {
  void local.navigate(tag);
}
</script>

<template>
  <section class="tags-ui" data-testid="kit-tags">
    <header class="tags-ui__header">
      <h2 class="tags-ui__title">Tags</h2>
      <p class="tags-ui__lede">
        Chips show the tag body only; a namespace colour dot and the tooltip carry
        the qualifier. The interface language picks the translated display name
        without another request.
      </p>
    </header>

    <div class="tags-ui__block" data-testid="kit-tags-sizes">
      <h3 class="tags-ui__subtitle">Chip sizes</h3>
      <div class="tags-ui__row" data-testid="tag-size-24" data-size="24">
        <code class="tags-ui__token">24</code>
        <TagChip :tag="showcaseTag" :size="24" />
        <TagChip :tag="namespaceTags[1]" :size="24" />
        <TagChip :tag="namespaceTags[2]" :size="24" />
        <TagChip :tag="namespaceTags[3]" :size="24" />
      </div>
      <div class="tags-ui__row" data-testid="tag-size-28" data-size="28">
        <code class="tags-ui__token">28</code>
        <TagChip :tag="showcaseTag" :size="28" />
        <TagChip :tag="namespaceTags[4]" :size="28" />
        <TagChip :tag="namespaceTags[5]" :size="28" />
        <TagChip :tag="namespaceTags[6]" :size="28" />
      </div>
    </div>

    <div class="tags-ui__block" data-testid="kit-tags-inline">
      <h3 class="tags-ui__subtitle">Inline truncation</h3>
      <div class="tags-ui__row">
        <code class="tags-ui__token">4 + 12</code>
        <span data-testid="tag-list-truncated">
          <TagList :tags="returnedTags" :tag-count="allTags.length" :max="4" :size="24" />
        </span>
      </div>
      <div class="tags-ui__row">
        <code class="tags-ui__token">4 of 8</code>
        <span data-testid="tag-list-full">
          <TagList :tags="fullTags" :max="4" :size="24" />
        </span>
      </div>
      <p class="tags-ui__hint">The +N chip opens the full list; language tags stay out of inline slots.</p>
    </div>

    <div class="tags-ui__block" data-testid="kit-tags-language">
      <h3 class="tags-ui__subtitle">Language follows the interface</h3>
      <div class="tags-ui__row">
        <TagChip :tag="showcaseTag" :size="28" data-testid="tag-showcase-chip" />
        <span class="tags-ui__raw">{{ tagRawText(showcaseTag) }}</span>
      </div>
      <p class="tags-ui__hint">
        Chinese shows the backend display translation; English shows the raw name.
        Switching the language must not request any /api endpoint.
      </p>
    </div>

    <div class="tags-ui__block" data-testid="kit-tags-link">
      <h3 class="tags-ui__subtitle">Inside a card link</h3>
      <RouterLink to="/browse" class="tags-ui__link" data-testid="tags-link-sample">
        <TagChip :tag="linkTag" :size="24" data-testid="tag-in-link" />
        <span class="tags-ui__link-label">This chip must not open the link</span>
      </RouterLink>
    </div>

    <div class="tags-ui__block" data-testid="kit-tags-menu">
      <h3 class="tags-ui__subtitle">Long press / right click</h3>
      <div class="tags-ui__row">
        <TagChip
          :tag="showcaseTag"
          :size="24"
          data-testid="tag-menu-trigger"
          @menu="openMenu"
        />
        <TagChip
          :tag="linkTag"
          :size="24"
          data-testid="tag-nav-local"
          @select="navigateLocal"
        />
      </div>
      <p class="tags-ui__hint">
        The menu copies the raw tag, filters the local library, searches online or excludes
        the tag; the second chip filters the library directly.
      </p>
    </div>

    <div class="tags-ui__block" data-testid="kit-tags-namespaces">
      <h3 class="tags-ui__subtitle">Namespace dots</h3>
      <div class="tags-ui__namespace-row">
        <TagChip
          v-for="tag in namespaceTags"
          :key="tagKey(tag)"
          :tag="tag"
          :size="24"
        />
      </div>
    </div>

    <TagMenu
      v-if="menu"
      :tag="menu.tag"
      :x="menu.x"
      :y="menu.y"
      source="local"
      @close="menu = null"
    />
  </section>
</template>

<style scoped>
.tags-ui {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
}

.tags-ui__header {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.tags-ui__title {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-large);
}

.tags-ui__subtitle {
  margin: 0;
  color: var(--gv-color-on-surface);
  font: var(--gv-type-title-small);
}

.tags-ui__lede,
.tags-ui__hint {
  margin: 0;
  max-width: 72ch;
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-body-small);
}

.tags-ui__block {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-2);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-md);
  background: var(--gv-color-surface-container);
}

.tags-ui__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  min-height: var(--gv-size-control-sm);
}

.tags-ui__token {
  min-width: 4rem;
  color: var(--gv-color-primary-text);
  font: var(--gv-type-label-large);
}

.tags-ui__raw {
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.tags-ui__link {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--gv-space-2);
  padding: var(--gv-space-2);
  border: 1px dashed var(--gv-color-outline);
  border-radius: var(--gv-radius-xs);
  color: var(--gv-color-primary-text);
  font: var(--gv-type-body-small);
  text-decoration: none;
}

.tags-ui__link-label {
  color: var(--gv-color-on-surface-variant);
}

.tags-ui__namespace-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gv-space-1);
}

@media (max-width: 599.98px) {
  .tags-ui__block {
    padding: var(--gv-space-3);
  }

  .tags-ui__row {
    align-items: flex-start;
  }
}
</style>
