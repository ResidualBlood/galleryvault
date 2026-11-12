/**
 * Server-proxy fallback page source (`…/pages/{n}/image`).
 *
 * Enabled per device via `gv_online_image_mode=proxy` when direct H@H fetches
 * do not work (blocked port, TLS interception, ...). This path spends the
 * backend image budget, so it is never the default.
 */
import { onlineImagePath } from "@/api/eh-reader";
import { officialGalleryUrl } from "@/api/eh";
import type { PageRef, PageSource, PageSourceKind } from "../source";

export class OnlineProxyPageSource implements PageSource {
  readonly kind: PageSourceKind = "online-proxy";

  constructor(
    private readonly gid: number,
    private readonly token: string,
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
      url: onlineImagePath(this.gid, this.token, index + 1),
    });
  }

  officialUrl(): string | null {
    return this.gid > 0 && this.token ? officialGalleryUrl(this.gid, this.token) : null;
  }
}
