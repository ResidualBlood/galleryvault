import { computed, ref, type ComputedRef, type Ref } from "vue";

export interface GallerySelection {
  ids: ComputedRef<ReadonlySet<number>>;
  count: ComputedRef<number>;
  has: (id: number) => boolean;
  toggle: (id: number, checked?: boolean) => void;
  addAll: (ids: number[]) => void;
  clear: () => void;
  list: ComputedRef<number[]>;
}

/**
 * Selection state for the library grid. It lives in the view (not the store)
 * so route-query changes do not clear the user's selection, and it survives
 * infinite scrolling because ids are additive.
 */
export function useGallerySelection(): GallerySelection {
  const state: Ref<Set<number>> = ref(new Set());
  const ids = computed<ReadonlySet<number>>(() => state.value);
  const count = computed(() => state.value.size);
  const list = computed(() => [...state.value]);

  function has(id: number): boolean {
    return state.value.has(id);
  }

  function toggle(id: number, checked?: boolean): void {
    const next = new Set(state.value);
    const shouldAdd = checked ?? !next.has(id);
    if (shouldAdd) next.add(id);
    else next.delete(id);
    state.value = next;
  }

  function addAll(ids: number[]): void {
    const next = new Set(state.value);
    for (const id of ids) next.add(id);
    state.value = next;
  }

  function clear(): void {
    state.value = new Set();
  }

  return { ids, count, has, toggle, addAll, clear, list };
}
