<script setup lang="ts">
/**
 * Local-library filter panel (DESIGN.md C19, audit LB-01 / LB-02 / LB-04 / LB-06).
 *
 * Desktop renders it as an inline, collapsible panel below the toolbar; below
 * 600px the page puts the same component inside a Sheet. Every field is a
 * `Field` plus a shared control in an equal-width grid, so the four selects can
 * no longer end at four different x positions and no row mixes 32px buttons with
 * 48px fields.
 *
 * Inputs are bound to the model directly (no local copy): the page owns the
 * object, pushes the URL on `commit` and derives the request from it. `commit`
 * fires on `change` for text/number/date fields, so typing does not refetch on
 * every keystroke.
 */
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Field from "@/components/ui/Field.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import type { GalleryListQuery } from "@/stores/library";
import type { GalleryList } from "@/api/lists";
import { languageFromTags, withLanguageTag, type LibraryFilters } from "./filters";
import LibrarySaveBar from "./manage/LibrarySaveBar.vue";
import LibraryFilteredDelete from "./manage/LibraryFilteredDelete.vue";

const props = defineProps<{
  modelValue: LibraryFilters;
  lists: GalleryList[];
  query: GalleryListQuery;
}>();

const emit = defineEmits<{
  "update:modelValue": [filters: LibraryFilters];
  commit: [];
  clear: [];
  "lists-changed": [];
  removed: [];
}>();

const { t } = useI18n();

const CATEGORY_KEYS: Record<string, string> = {
  doujinshi: "catDoujinshi",
  manga: "catManga",
  artistcg: "catArtistcg",
  gamecg: "catGamecg",
  western: "catWestern",
  "non-h": "catNonH",
  image_set: "catImageSet",
  cosplay: "catCosplay",
  asianporn: "catAsianporn",
  misc: "catMisc",
  deleted: "catDeleted",
};

function categoryLabel(value: string): string {
  return t(`legacy.${CATEGORY_KEYS[value] ?? "catMisc"}`);
}

const categoryOptions = computed(() => [
  { value: "", label: t("legacy.allCategories") },
  ...Object.keys(CATEGORY_KEYS).map((value) => ({ value, label: categoryLabel(value) })),
  { value: "__not_fav__", label: t("legacy.notFavorited") },
]);

const readStatusOptions = computed(() => [
  { value: "", label: t("legacy.readStatusAll") },
  { value: "unread", label: t("legacy.readStatusUnread") },
  { value: "reading", label: t("legacy.readStatusReading") },
  { value: "completed", label: t("legacy.readStatusCompleted") },
]);

const ratingOptions = computed(() => [
  { value: "", label: t("legacy.minRating") },
  { value: "2", label: "≥2" },
  { value: "3", label: "≥3" },
  { value: "4", label: "≥4" },
  { value: "4.5", label: "≥4.5" },
]);

const qualityOptions = computed(() => [
  { value: "", label: t("legacy.qualityAll") },
  { value: "original", label: t("legacy.qualityOriginal") },
  { value: "resample", label: t("legacy.qualityResample") },
]);

const localRatingOptions = computed(() => [
  { value: "", label: t("legacy.localRatingMin") },
  ...[1, 2, 3, 4, 5].map((value) => ({
    value: String(value),
    label: t("library.page.localRatingOption", { value }),
  })),
]);

const languageOptions = computed(() => [
  { value: "", label: t("legacy.languageAll") },
  { value: "chinese", label: t("legacy.langChinese") },
  { value: "english", label: t("legacy.langEnglish") },
  { value: "japanese", label: t("legacy.langJapanese") },
  { value: "korean", label: t("legacy.langKorean") },
  { value: "translated", label: t("legacy.langTranslated") },
]);

const listOptions = computed(() => [
  { value: "", label: t("libraryManage.listFilterAll") },
  ...props.lists.map((item) => ({
    value: String(item.id),
    label: `${item.name} (${item.count ?? 0})`,
  })),
]);

const pageSizeOptions = computed(() => {
  const values = new Set([24, 50, 100, 200, 500, props.modelValue.pageSize]);
  return [...values]
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((a, b) => a - b)
    .map((value) => ({ value: String(value), label: String(value) }));
});

const language = computed(() => languageFromTags(props.modelValue.tags));

function patch(part: Partial<LibraryFilters>): void {
  emit("update:modelValue", { ...props.modelValue, ...part });
}

function onLanguage(value: string): void {
  patch({ tags: withLanguageTag(props.modelValue.tags, value) });
  emit("commit");
}

function commit(): void {
  emit("commit");
}
</script>

<template>
  <section
    id="library-advanced-filters"
    class="filter-panel"
    data-testid="advanced-filters"
    :aria-label="t('library.page.filtersTitle')"
  >
    <div class="filter-panel__grid">
      <Field :label="t('library.page.categoryLabel')" label-for="library-filter-category">
        <Select
          id="library-filter-category"
          data-testid="category-filter"
          :model-value="modelValue.category"
          :options="categoryOptions"
          @update:model-value="patch({ category: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('library.page.readStatusLabel')" label-for="library-filter-read">
        <Select
          id="library-filter-read"
          :model-value="modelValue.readStatus"
          :options="readStatusOptions"
          @update:model-value="patch({ readStatus: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('library.page.languageLabel')" label-for="library-filter-language">
        <Select
          id="library-filter-language"
          data-testid="language-filter"
          :model-value="language"
          :options="languageOptions"
          @update:model-value="onLanguage"
        />
      </Field>
      <Field :label="t('legacy.minRating')" label-for="library-filter-rating">
        <Select
          id="library-filter-rating"
          data-testid="min-rating"
          :model-value="modelValue.minRating"
          :options="ratingOptions"
          @update:model-value="patch({ minRating: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.pageMin')" label-for="library-filter-page-min">
        <Input
          id="library-filter-page-min"
          data-testid="page-min"
          type="number"
          :model-value="modelValue.pageMin"
          @update:model-value="patch({ pageMin: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.pageMax')" label-for="library-filter-page-max">
        <Input
          id="library-filter-page-max"
          data-testid="page-max"
          type="number"
          :model-value="modelValue.pageMax"
          @update:model-value="patch({ pageMax: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.sizeMin')" label-for="library-filter-size-min">
        <Input
          id="library-filter-size-min"
          data-testid="size-min"
          type="number"
          :model-value="modelValue.sizeMin"
          @update:model-value="patch({ sizeMin: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.sizeMax')" label-for="library-filter-size-max">
        <Input
          id="library-filter-size-max"
          data-testid="size-max"
          type="number"
          :model-value="modelValue.sizeMax"
          @update:model-value="patch({ sizeMax: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.postedFrom')" label-for="library-filter-posted-from">
        <Input
          id="library-filter-posted-from"
          data-testid="posted-from"
          type="date"
          :model-value="modelValue.postedFrom"
          @update:model-value="patch({ postedFrom: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.postedTo')" label-for="library-filter-posted-to">
        <Input
          id="library-filter-posted-to"
          data-testid="posted-to"
          type="date"
          :model-value="modelValue.postedTo"
          @update:model-value="patch({ postedTo: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.uploader')" label-for="library-filter-uploader">
        <Input
          id="library-filter-uploader"
          data-testid="uploader-filter"
          :model-value="modelValue.uploader"
          @update:model-value="patch({ uploader: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.localRatingMin')" label-for="library-filter-local-rating">
        <Select
          id="library-filter-local-rating"
          data-testid="min-local-rating"
          :model-value="modelValue.minLocalRating"
          :options="localRatingOptions"
          @update:model-value="patch({ minLocalRating: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('legacy.quality')" label-for="library-filter-quality">
        <Select
          id="library-filter-quality"
          data-testid="image-quality"
          :model-value="modelValue.imageQuality"
          :options="qualityOptions"
          @update:model-value="patch({ imageQuality: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('libraryManage.listFilter')" label-for="library-filter-list">
        <Select
          id="library-filter-list"
          data-testid="list-filter"
          :model-value="modelValue.listId"
          :options="listOptions"
          @update:model-value="patch({ listId: $event })"
          @change="commit"
        />
      </Field>
      <Field :label="t('library.page.pageSizeLabel')" label-for="library-filter-page-size">
        <Select
          id="library-filter-page-size"
          data-testid="page-size-select"
          :model-value="String(modelValue.pageSize)"
          :options="pageSizeOptions"
          @update:model-value="patch({ pageSize: Number($event) })"
          @change="commit"
        />
      </Field>
    </div>

    <LibrarySaveBar
      :query="query"
      @lists-changed="emit('lists-changed')"
    />

    <div class="filter-panel__footer">
      <Button variant="outlined" icon="close" data-testid="library-clear-filters" @click="emit('clear')">
        {{ t("library.page.clearFilters") }}
      </Button>
      <LibraryFilteredDelete :query="query" @removed="emit('removed')" />
    </div>
  </section>
</template>

<style scoped>
.filter-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-4);
  padding: var(--gv-space-4);
  border: 1px solid var(--gv-color-outline-variant);
  border-radius: var(--gv-radius-lg);
  background: var(--gv-color-surface-container-low);
}

.filter-panel__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--gv-space-3) var(--gv-space-4);
}

.filter-panel__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--gv-space-2);
}

@media (max-width: 599.98px) {
  .filter-panel {
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
  }

  .filter-panel__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
