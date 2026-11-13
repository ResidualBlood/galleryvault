<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import {
  useFavoritesStore,
  parseFavcat,
  readDefaultFavcat,
  rememberDefaultFavcat,
} from "@/stores/favorites";
import { useUiStore } from "@/stores/ui";
import { ensureActionMessages } from "./messages";

ensureActionMessages();

const props = defineProps<{
  gid: number;
  token: string;
  favorited: boolean;
  favcat: number | null;
  note?: string | null;
  disabled?: boolean;
  heading?: boolean;
}>();

const emit = defineEmits<{ done: [] }>();

const { t } = useI18n();
const store = useFavoritesStore();
const ui = useUiStore();

const withHeading = props.heading ?? true;
const selected = ref<number>(parseFavcat(props.favcat) ?? readDefaultFavcat() ?? 0);
const note = ref(props.note ?? "");
const submitting = ref(false);

const categories = computed(() => {
  if (store.categories.length) return store.categories;
  return Array.from({ length: 10 }, (_, index) => ({
    favcat: index,
    name: "",
    cloud_count: null,
  }));
});

const current = computed(() => parseFavcat(props.favcat));
const noteChanged = computed(() => props.favorited && note.value !== (props.note ?? ""));

function folderName(favcat: number, name: string): string {
  return name || t("actions.folder", { index: favcat });
}

function colorFor(favcat: number): string {
  return `var(--gv-favcat-${favcat})`;
}

onMounted(() => {
  const fallback = parseFavcat(props.favcat) ?? readDefaultFavcat();
  if (fallback !== null) selected.value = fallback;
  void store.loadCategories().catch(() => {
    /* fall back to the ten empty slots */
  });
});

async function submit(): Promise<void> {
  if (submitting.value || props.disabled) return;
  submitting.value = true;
  try {
    if (!props.favorited) {
      const result = await store.add(props.gid, props.token, selected.value, note.value.trim());
      if (!result.ok) {
        ui.error(t("actions.favoriteFailed"));
        return;
      }
      rememberDefaultFavcat(selected.value);
      ui.success(t("actions.favoriteAdded"));
      emit("done");
      return;
    }

    if (selected.value !== current.value) {
      const result = await store.move(props.gid, selected.value);
      if (!result.ok) {
        ui.error(t("actions.favoriteMoveFailed"));
        return;
      }
      rememberDefaultFavcat(selected.value);
      ui.success(t("actions.favoriteMoved"));
    }

    if (noteChanged.value) {
      const ok = await store.updateNote(props.gid, note.value.trim());
      if (!ok) {
        ui.error(t("actions.noteFailed"));
        return;
      }
      ui.success(t("actions.noteSaved"));
    }

    emit("done");
  } catch {
    ui.error(
      props.favorited
        ? selected.value !== current.value
          ? t("actions.favoriteMoveFailed")
          : t("actions.noteFailed")
        : t("actions.favoriteFailed"),
    );
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="fav-panel" data-testid="fav-panel">
    <p v-if="withHeading" class="fav-panel__title">{{ t("actions.favoriteSelect") }}</p>
    <div class="fav-panel__grid" role="radiogroup" :aria-label="t('actions.favoriteSelect')">
      <Button
        v-for="category in categories"
        :key="category.favcat"
        class="fav-panel__slot"
        :class="{ 'fav-panel__slot--selected': selected === category.favcat }"
        :variant="selected === category.favcat ? 'tonal' : 'text'"
        size="md"
        role="radio"
        :aria-checked="selected === category.favcat"
        :data-testid="`fav-cat-${category.favcat}`"
        :data-favcat="category.favcat"
        @click="selected = category.favcat"
      >
        <template #leading>
          <span class="fav-panel__dot" :style="{ background: colorFor(category.favcat) }" />
        </template>
        <span class="fav-panel__name">{{ folderName(category.favcat, category.name) }}</span>
        <template v-if="current === category.favcat" #trailing>
          <span class="fav-panel__current">{{ t("actions.current") }}</span>
        </template>
      </Button>
    </div>

    <Input
      v-model="note"
      class="fav-panel__note"
      :label="t('actions.note')"
      :placeholder="t('actions.notePlaceholder')"
      size="md"
      data-testid="fav-note"
    />

    <div class="fav-panel__footer">
      <Button variant="text" :disabled="submitting" @click="emit('done')">
        {{ t("actions.cancel") }}
      </Button>
      <Button
        variant="filled"
        :loading="submitting"
        :disabled="disabled"
        data-testid="fav-confirm"
        @click="submit"
      >
        {{ t("actions.confirm") }}
      </Button>
    </div>
  </div>
</template>

<style scoped>
.fav-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-3);
  min-width: 240px;
}

.fav-panel__title {
  margin: 0;
  font: var(--gv-type-title-small);
  color: var(--gv-color-on-surface);
}

.fav-panel__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--gv-space-1);
}

@media (max-width: 599px) {
  .fav-panel__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.fav-panel__slot {
  justify-content: flex-start;
  width: 100%;
}

.fav-panel__slot--selected {
  border-color: var(--gv-color-primary);
}

.fav-panel__dot {
  flex: none;
  width: var(--gv-space-3);
  height: var(--gv-space-3);
  border: 1px solid var(--gv-color-outline);
  border-radius: var(--gv-radius-full);
}

.fav-panel__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fav-panel__current {
  font: var(--gv-type-label-small);
  color: var(--gv-color-on-surface-variant);
}

.fav-panel__note {
  min-width: 0;
}

.fav-panel__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gv-space-2);
}
</style>
