/**
 * Adapters between `/api/galleries/trash|expunged` and the shared collection
 * surface (PLAN polish §P5 / C18).
 *
 * Recycle entries carry fewer fields than a library gallery: there is no
 * uploader, rating, size or favourite state. Fill the fields that exist and
 * leave the rest empty so `GalleryCard` / `GalleryListRow` render the shared
 * card without inventing values. The deletion / expunged date becomes the
 * card's meta date and is also surfaced as a status badge by the view.
 */
import type { GalleryItem } from "@/api/library";
import type { ExpungedGallery, TrashGallery } from "@/api/recycle";
import { formatDate } from "@/stores/library";

export type RecycleItem = TrashGallery | ExpungedGallery;

export function isTrashItem(item: RecycleItem): item is TrashGallery {
  return "trashed_at" in item;
}

/** Deletion date for user-deleted rows, last update for scan-expunged rows. */
export function recycleDate(item: RecycleItem): string {
  const iso = isTrashItem(item) ? item.trashed_at : item.updated_at;
  return formatDate(iso);
}

export function recycleToGalleryItem(item: RecycleItem, statusLabel: string): GalleryItem {
  return {
    id: item.id,
    gid: item.gid ?? null,
    token: item.token ?? null,
    title: item.title || `#${item.id}`,
    category: isTrashItem(item) ? item.category || "other" : "other",
    page_count: item.page_count,
    cover_url: item.cover_url ?? null,
    tags: item.tags ?? [],
    tag_count: item.tag_count ?? item.tags?.length ?? 0,
    // The shared card only knows a generic "uploader / author" line; the
    // recycle status ("user deleted" / "missing on disk") is the closest
    // meaningful value and keeps the line from starting with an em dash.
    uploader: statusLabel,
    posted_at: isTrashItem(item) ? item.trashed_at ?? null : item.updated_at ?? null,
    reading_progress: isTrashItem(item) ? item.reading_progress ?? null : null,
  };
}
