import type { PageProgress, PageRef, PageSource, PageSourceKind } from "./source";
import { readerPagePath, saveReaderProgress } from "@/api/reader";

/** Pages served by the GalleryVault backend (`/api/galleries/{id}/pages/{n}`). */
export class LocalPageSource implements PageSource {
  readonly kind: PageSourceKind = "local";

  constructor(
    private readonly galleryId: number | string,
    readonly pageCount: number | null,
  ) {}

  page(index: number): Promise<PageRef> {
    if (!Number.isInteger(index) || index < 0) {
      return Promise.reject(new RangeError(`invalid page index: ${index}`));
    }
    if (this.pageCount !== null && index >= this.pageCount) {
      return Promise.reject(new RangeError(`page ${index} out of range`));
    }
    return Promise.resolve({
      index,
      url: readerPagePath(this.galleryId, index),
    });
  }

  officialUrl(): string | null {
    return null;
  }

  /** Local galleries persist to the local progress endpoint. */
  saveProgress(progress: PageProgress): Promise<unknown> {
    return saveReaderProgress(this.galleryId, progress);
  }
}
