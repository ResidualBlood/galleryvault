import { reactive, ref } from "vue";
import { defineStore } from "pinia";
import {
  addFavorite,
  fetchFavoriteCategories,
  moveFavorite,
  removeFavorite,
  setFavoriteNote,
  type FavoriteCategory,
} from "@/api/favorites";

/** Legacy-compatible quick-action preference (PLAN §4.2 group 4). */
export const DEFAULT_FAVCAT_KEY = "gv_default_favcat";

export interface FavoriteEntry {
  favorited: boolean;
  favcat: number | null;
  note: string | null;
  pending: boolean;
}

export interface FavoriteSeed {
  favorited?: boolean;
  favcat?: number | null;
  note?: string | null;
}

export interface FavoriteMutationOutcome {
  ok: boolean;
  cloudFailed: number[];
}

export function parseFavcat(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 9) return null;
  return parsed;
}

export function readDefaultFavcat(): number | null {
  try {
    return parseFavcat(localStorage.getItem(DEFAULT_FAVCAT_KEY));
  } catch {
    return null;
  }
}

export function rememberDefaultFavcat(favcat: number): number | null {
  const parsed = parseFavcat(favcat);
  if (parsed === null) return null;
  try {
    localStorage.setItem(DEFAULT_FAVCAT_KEY, String(parsed));
  } catch {
    /* storage may be blocked; the value is still returned for this click */
  }
  return parsed;
}

function emptyEntry(): FavoriteEntry {
  return { favorited: false, favcat: null, note: null, pending: false };
}

/**
 * Quick favorite state, keyed by gid and shared by cards / detail / reader.
 *
 * Hard rule (PLAN §4.1): no optimistic updates. `add` / `move` / `remove` /
 * `note` only mutate local state after the backend reports the gid in
 * `successful_gids` (i.e. ExHentai confirmed the change). HTTP errors leave
 * state untouched and are re-thrown for the caller to surface as a toast.
 */
export const useFavoritesStore = defineStore("favorites", () => {
  const entries = reactive<Record<number, FavoriteEntry>>({});
  const categories = ref<FavoriteCategory[]>([]);
  const loadingCategories = ref(false);
  const inflight = new Map<number, Promise<FavoriteMutationOutcome>>();
  const noteInflight = new Map<number, Promise<boolean>>();
  let categoriesPromise: Promise<FavoriteCategory[]> | null = null;

  function ensure(gid: number, seed?: FavoriteSeed): FavoriteEntry {
    if (!entries[gid]) {
      entries[gid] = {
        ...emptyEntry(),
        favorited: Boolean(seed?.favorited),
        favcat: parseFavcat(seed?.favcat ?? null),
        note: seed?.note ?? null,
      };
    }
    return entries[gid];
  }

  function get(gid: number): FavoriteEntry {
    return entries[gid] ?? ensure(gid);
  }

  function isPending(gid: number): boolean {
    return Boolean(entries[gid]?.pending);
  }

  function applyFavorite(gid: number, favcat: number, note?: string | null): void {
    const entry = ensure(gid);
    entry.favorited = true;
    entry.favcat = parseFavcat(favcat);
    if (note !== undefined) entry.note = note;
  }

  function applyRemoved(gid: number): void {
    const entry = ensure(gid);
    entry.favorited = false;
    entry.favcat = null;
    entry.note = null;
  }

  async function loadCategories(force = false): Promise<FavoriteCategory[]> {
    if (!force && categories.value.length) return categories.value;
    if (!force && categoriesPromise) return categoriesPromise;
    loadingCategories.value = true;
    categoriesPromise = fetchFavoriteCategories()
      .then((items) => {
        categories.value = items;
        return items;
      })
      .catch((error: unknown) => {
        categoriesPromise = null;
        throw error;
      })
      .finally(() => {
        loadingCategories.value = false;
      });
    return categoriesPromise;
  }

  function shared(
    gid: number,
    run: () => Promise<FavoriteMutationOutcome>,
  ): Promise<FavoriteMutationOutcome> {
    const existing = inflight.get(gid);
    if (existing) return existing;
    const entry = ensure(gid);
    entry.pending = true;
    const promise = run().finally(() => {
      inflight.delete(gid);
      entry.pending = false;
    });
    inflight.set(gid, promise);
    return promise;
  }

  async function add(
    gid: number,
    token: string,
    targetFavcat: number,
    note = "",
  ): Promise<FavoriteMutationOutcome> {
    return shared(gid, async () => {
      const result = await addFavorite({ gid, token, target_favcat: targetFavcat, note });
      const ok = result.cloud_ok && result.successful_gids.includes(gid);
      if (ok) {
        applyFavorite(gid, targetFavcat, note);
        rememberDefaultFavcat(targetFavcat);
      }
      return { ok, cloudFailed: result.cloud_failed };
    });
  }

  async function move(gid: number, targetFavcat: number): Promise<FavoriteMutationOutcome> {
    return shared(gid, async () => {
      const result = await moveFavorite([gid], targetFavcat);
      const ok = result.cloud_ok && result.successful_gids.includes(gid);
      if (ok) applyFavorite(gid, targetFavcat);
      return { ok, cloudFailed: result.cloud_failed };
    });
  }

  async function remove(gid: number): Promise<FavoriteMutationOutcome> {
    return shared(gid, async () => {
      const result = await removeFavorite([gid]);
      const ok = result.cloud_ok && result.successful_gids.includes(gid);
      if (ok) applyRemoved(gid);
      return { ok, cloudFailed: result.cloud_failed };
    });
  }

  function updateNote(gid: number, note: string): Promise<boolean> {
    const existing = noteInflight.get(gid);
    if (existing) return existing;
    const entry = ensure(gid);
    entry.pending = true;
    const promise = setFavoriteNote(gid, note)
      .then((result) => {
        if (!result.cloud_ok) return false;
        entry.note = note;
        return true;
      })
      .finally(() => {
        noteInflight.delete(gid);
        entry.pending = false;
      });
    noteInflight.set(gid, promise);
    return promise;
  }

  return {
    entries,
    categories,
    loadingCategories,
    ensure,
    get,
    isPending,
    loadCategories,
    add,
    move,
    remove,
    updateNote,
    applyFavorite,
    applyRemoved,
  };
});
