/** Shared maintenance helpers: the legacy frontend whitelisted every
 * server-provided URL before it reached `href` / `src` (inv-frontend.md §8.1);
 * the rewrite keeps the same rule in one place. */

/** Server-provided links: allow http(s), hash and root-relative paths only. */
export function safeHref(value: unknown): string {
  const text = String(value ?? "").trim();
  if (text.includes("\\")) return "#";
  return /^(https?:\/\/|#|\/(?!\/))/i.test(text) ? text : "#";
}

/** Covers may be data images, http(s) or root-relative paths. */
export function coverSrc(value: unknown): string {
  const text = String(value ?? "").trim();
  if (text.includes("\\")) return "";
  return /^(data:image\/(png|jpeg|gif|webp);base64,|https?:\/\/|\/(?!\/))/i.test(text)
    ? text
    : "";
}

export function galleryThumbUrl(galleryId: number, page = 0): string {
  return `/api/galleries/${galleryId}/thumb/${page}`;
}
