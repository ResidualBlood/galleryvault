import { ep, request } from "./client";

export const integrityGalleriesEp = ep("GET", "/api/galleries/integrity");
export const scanIntegrityEp = ep("POST", "/api/galleries/integrity/scan");
export const redownloadGalleryEp = ep("POST", "/api/galleries/{id}/redownload");

export interface IntegrityTag {
  namespace: string | null;
  name: string;
  display?: string | null;
}

export interface IntegrityGallery {
  id: number;
  gid?: number | null;
  title: string;
  page_count: number;
  actual_pages: number;
  file_count?: number | null;
  cover_url?: string | null;
  storage_path?: string | null;
  tags?: IntegrityTag[];
}

export interface IntegrityScanSummary {
  running: boolean;
  started_at?: string | null;
  completed_at?: string | null;
  scanned: number;
  total: number;
  corrupt: number;
}

export interface IntegrityPage {
  total: number;
  page: number;
  page_size: number;
  magic_scan: IntegrityScanSummary;
  items: IntegrityGallery[];
}

export interface IntegrityScanResult extends IntegrityScanSummary {
  status?: "paused" | string;
  detail?: string;
}

export function fetchIntegrity(
  page = 1,
  pageSize = 24,
  signal?: AbortSignal,
): Promise<IntegrityPage> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return request<IntegrityPage>(
    { method: integrityGalleriesEp.method, path: `${integrityGalleriesEp.path}?${params}` },
    { signal },
  );
}

export function scanIntegrity(signal?: AbortSignal): Promise<IntegrityScanResult> {
  return request<IntegrityScanResult>(scanIntegrityEp, { signal });
}

export function redownloadGallery(id: number, signal?: AbortSignal): Promise<unknown> {
  return request(
    {
      method: redownloadGalleryEp.method,
      path: redownloadGalleryEp.path.replace("{id}", String(id)),
    },
    { signal },
  );
}
