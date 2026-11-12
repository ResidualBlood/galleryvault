/**
 * Online page-source factory.
 *
 * The reader UI picks the mode once per mount; switching modes remounts the
 * reader shell so every cached URL is re-derived through the new source.
 */
import type { PageSource } from "../source";
import { OnlineDirectPageSource } from "./online-direct";
import { OnlineProxyPageSource } from "./online-proxy";
import type { OnlineImageMode } from "./mode";

export { OnlineDirectPageSource } from "./online-direct";
export { OnlineProxyPageSource } from "./online-proxy";
export {
  DEFAULT_ONLINE_IMAGE_MODE,
  ONLINE_IMAGE_MODE_KEY,
  ONLINE_IMAGE_MODES,
  isOnlineImageMode,
  readOnlineImageMode,
  writeOnlineImageMode,
  type OnlineImageMode,
} from "./mode";
export {
  ONLINE_EXPIRY_SKEW_MS,
  ONLINE_MAX_RESOLVE_IN_FLIGHT,
  ONLINE_PLACEHOLDER_MAX_EDGE,
  OnlineSourceError,
  isPlaceholderSize,
  type OnlineImageSize,
  type OnlineSourceErrorCode,
  type OnlineSourceEvent,
} from "./online-direct";

export interface OnlinePageSourceOptions {
  mode: OnlineImageMode;
  gid: number;
  token: string;
  pageCount: number | null;
}

export function createOnlinePageSource(options: OnlinePageSourceOptions): PageSource {
  if (options.mode === "proxy") {
    return new OnlineProxyPageSource(options.gid, options.token, options.pageCount);
  }
  return new OnlineDirectPageSource({
    gid: options.gid,
    token: options.token,
    pageCount: options.pageCount,
  });
}
