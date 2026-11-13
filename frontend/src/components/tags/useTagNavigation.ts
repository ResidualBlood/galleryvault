import { useRoute, useRouter, type LocationQueryRaw, type RouteLocationRaw } from "vue-router";
import { formatEhTagQuery, libraryTagQuery, type TagLike } from "./tag-utils";

export type TagSource = "local" | "favorites" | "series" | "online";

export interface TagNavigationOptions {
  exclude?: boolean;
}

export interface TagNavigation {
  /** Where a click would go, without navigating (used by tests / tooltips). */
  destination: (tag: TagLike, options?: TagNavigationOptions) => RouteLocationRaw;
  navigate: (tag: TagLike, options?: TagNavigationOptions) => Promise<unknown>;
}

/**
 * Clicking a tag filters the local library (local / favorites / series) or
 * re-runs an online search. Local filters append to the current `tags=` value
 * with `tag_mode=and`; online searches use ExHentai's exact `ns:"name$"`
 * syntax. Both helpers are idempotent, so repeated clicks are harmless.
 */
export function useTagNavigation(source: TagSource = "local"): TagNavigation {
  const router = useRouter();
  const route = useRoute();

  function destination(
    tag: TagLike,
    options: TagNavigationOptions = {},
  ): RouteLocationRaw {
    if (source === "online") {
      const query = `${options.exclude ? "-" : ""}${formatEhTagQuery(
        tag.namespace,
        tag.name,
      )}`;
      return { name: "online", query: { q: query } };
    }

    const current = route.name === "library" ? (route.query as LocationQueryRaw) : undefined;
    const filter = libraryTagQuery(current, tag, options);
    const query: LocationQueryRaw = {
      ...(current ?? {}),
      tags: filter.tags,
      tag_mode: filter.tag_mode,
    };
    delete query.page;
    return { name: "library", query };
  }

  function navigate(tag: TagLike, options: TagNavigationOptions = {}): Promise<unknown> {
    return router.push(destination(tag, options));
  }

  return { destination, navigate };
}
