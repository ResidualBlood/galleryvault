/**
 * Adapter between `/api/galleries/integrity` and the shared collection surface
 * (PLAN polish §P5 / C18).
 *
 * Integrity rows have no uploader / posted date; the mismatch text is the one
 * piece of information the page is about, so it becomes the list sub-line and
 * the source of the status badge. Everything else stays empty rather than
 * being invented.
 */
import type { GalleryItem } from "@/api/library";
import type { IntegrityGallery } from "@/api/integrity";

export function missingPages(item: IntegrityGallery): number {
  return Math.abs(item.page_count - item.actual_pages);
}

export function integrityMismatchText(
  item: IntegrityGallery,
  translate: (key: string, named: Record<string, unknown>) => string,
): string {
  return translate("maintenance.integrity.mismatch", {
    declared: item.page_count,
    actual: item.actual_pages,
    files: item.file_count ?? translate("maintenance.integrity.fileUnknown", {}),
  });
}

export function integrityToGalleryItem(
  item: IntegrityGallery,
  mismatch: string,
): GalleryItem {
  return {
    id: item.id,
    gid: item.gid ?? null,
    token: null,
    title: item.title || `#${item.id}`,
    category: "other",
    page_count: item.page_count,
    cover_url: item.cover_url ?? null,
    tags: item.tags ?? [],
    tag_count: item.tag_count ?? item.tags?.length ?? 0,
    uploader: mismatch,
    posted_at: null,
    reading_progress: null,
  };
}
