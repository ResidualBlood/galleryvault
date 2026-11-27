import { ep, request } from "./client";

export const historyEp = ep("GET", "/api/history");
export const clearHistoryEp = ep("DELETE", "/api/history");
export const clearAllProgressEp = ep("DELETE", "/api/galleries/progress");
export const clearGalleryProgressEp = ep("DELETE", "/api/galleries/{id}/progress");

export interface HistoryEntry {
  gallery_id: number;
  current_page: number;
  total_pages: number | null;
  last_read_at: string | null;
  title: string | null;
  display_title: string | null;
  raw_title: string | null;
  title_jpn: string | null;
  gid: number | null;
  category: string | null;
  url: string | null;
}

export interface HistoryPage {
  total: number;
  page: number;
  page_size: number;
  items: HistoryEntry[];
}

function queryPath(path: string, params: URLSearchParams): string {
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

function normalizeEntry(raw: HistoryEntry): HistoryEntry {
  return {
    gallery_id: Number(raw?.gallery_id) || 0,
    current_page: Number(raw?.current_page) || 0,
    total_pages: typeof raw?.total_pages === "number" ? raw.total_pages : null,
    last_read_at: typeof raw?.last_read_at === "string" ? raw.last_read_at : null,
    title: typeof raw?.title === "string" ? raw.title : null,
    display_title: typeof raw?.display_title === "string" ? raw.display_title : null,
    raw_title: typeof raw?.raw_title === "string" ? raw.raw_title : null,
    title_jpn: typeof raw?.title_jpn === "string" ? raw.title_jpn : null,
    gid: typeof raw?.gid === "number" ? raw.gid : null,
    category: typeof raw?.category === "string" ? raw.category : null,
    url: typeof raw?.url === "string" ? raw.url : null,
  };
}

export async function fetchHistory(
  page = 1,
  pageSize = 24,
  signal?: AbortSignal,
): Promise<HistoryPage> {
  const params = new URLSearchParams({
    page: String(Math.max(1, Math.trunc(page) || 1)),
    page_size: String(Math.max(1, Math.trunc(pageSize) || 24)),
  });
  const data = await request<HistoryPage>(
    { method: historyEp.method, path: queryPath(historyEp.path, params) },
    { signal },
  );
  return {
    total: Number(data?.total) || 0,
    page: Number(data?.page) || page,
    page_size: Number(data?.page_size) || pageSize,
    items: Array.isArray(data?.items) ? data.items.map(normalizeEntry) : [],
  };
}

export async function clearHistory(signal?: AbortSignal): Promise<void> {
  const params = new URLSearchParams({ confirm: "true" });
  await request(
    { method: clearHistoryEp.method, path: queryPath(clearHistoryEp.path, params) },
    { signal },
  );
}

export async function clearAllProgress(signal?: AbortSignal): Promise<void> {
  const params = new URLSearchParams({ confirm: "true" });
  await request(
    {
      method: clearAllProgressEp.method,
      path: queryPath(clearAllProgressEp.path, params),
    },
    { signal },
  );
}

export async function clearGalleryProgress(
  galleryId: number,
  signal?: AbortSignal,
): Promise<void> {
  const path = clearGalleryProgressEp.path.replace("{id}", String(galleryId));
  await request({ method: clearGalleryProgressEp.method, path }, { signal });
}
