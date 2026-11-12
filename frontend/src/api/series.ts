import { request } from "./client";
import { downloadSelectedFavoritesEp } from "./favorites";
import {
  addSeriesCloudItemsEp,
  createSeriesEp,
  deleteSeriesEp,
  patchSeriesEp,
  rebuildSeriesEp,
  removeSeriesCloudItemsEp,
  removeSeriesItemsEp,
  seriesCloudCandidatesEp,
  seriesEp,
} from "./library";

export interface SeriesTag {
  namespace: string;
  name: string;
  display?: string | null;
}

export interface SeriesMember {
  /** Local gallery id (null for cloud-only members). */
  id: number | null;
  gallery_id: number | null;
  is_local: boolean;
  gid: number | null;
  token: string | null;
  favcat?: number | null;
  url?: string | null;
  title: string;
  category?: string | null;
  page_count?: number;
  cover_url?: string | null;
  tags?: SeriesTag[];
}

export interface SeriesGroup {
  id: number;
  name: string;
  match_key?: string | null;
  name_manual?: boolean | null;
  count: number;
  created_at?: string | null;
  galleries: SeriesMember[];
}

export interface SeriesPage {
  items: SeriesGroup[];
  total: number;
  page: number;
  page_size: number;
}

export interface SeriesCloudCandidate {
  gid: number;
  title?: string | null;
  thumb?: string | null;
  token?: string | null;
  favcat?: number | null;
}

export interface SeriesQuery {
  page?: number;
  page_size?: number;
  show_all?: boolean;
}

export interface AddSeriesCloudResult {
  id: number;
  added_local?: number;
  added_cloud?: number;
  skipped?: number;
}

export interface RemoveSeriesResult {
  id: number;
  removed?: number;
}

export function withId<M extends "GET" | "POST" | "PATCH" | "DELETE">(
  endpoint: { method: M; path: string },
  id: number,
): { method: M; path: string } {
  return { method: endpoint.method, path: endpoint.path.replace("{id}", String(id)) };
}

export function fetchSeries(
  query: SeriesQuery = {},
  signal?: AbortSignal,
): Promise<SeriesPage> {
  const params = new URLSearchParams();
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.page_size ?? 25));
  if (query.show_all) params.set("show_all", "1");
  return request<SeriesPage>({ method: seriesEp.method, path: `${seriesEp.path}?${params}` }, { signal });
}

export function createSeries(name: string, signal?: AbortSignal): Promise<SeriesGroup> {
  return request<SeriesGroup>(createSeriesEp, { body: { name }, signal });
}

export function renameSeries(
  id: number,
  name: string,
  signal?: AbortSignal,
): Promise<SeriesGroup> {
  return request<SeriesGroup>(withId(patchSeriesEp, id), { body: { name }, signal });
}

export function deleteSeries(id: number, signal?: AbortSignal): Promise<{ deleted?: boolean }> {
  return request<{ deleted?: boolean }>(withId(deleteSeriesEp, id), { signal });
}

export function rebuildSeries(
  signal?: AbortSignal,
): Promise<{ created?: number; merged?: number }> {
  return request<{ created?: number; merged?: number }>(rebuildSeriesEp, { signal });
}

export async function fetchSeriesCloudCandidates(
  id: number,
  q = "",
  signal?: AbortSignal,
): Promise<SeriesCloudCandidate[]> {
  const endpoint = withId(seriesCloudCandidatesEp, id);
  const path = q ? `${endpoint.path}?${new URLSearchParams({ q })}` : endpoint.path;
  const data = await request<{ items?: SeriesCloudCandidate[] }>(
    { method: endpoint.method, path },
    { signal },
  );
  return Array.isArray(data?.items) ? data.items : [];
}

export function addSeriesCloudItems(
  id: number,
  gids: number[],
  signal?: AbortSignal,
): Promise<AddSeriesCloudResult> {
  return request<AddSeriesCloudResult>(withId(addSeriesCloudItemsEp, id), {
    body: { gids },
    signal,
  });
}

export function removeSeriesCloudItems(
  id: number,
  gids: number[],
  signal?: AbortSignal,
): Promise<RemoveSeriesResult> {
  return request<RemoveSeriesResult>(withId(removeSeriesCloudItemsEp, id), {
    body: { gids },
    signal,
  });
}

export function removeSeriesItems(
  id: number,
  galleryIds: number[],
  signal?: AbortSignal,
): Promise<RemoveSeriesResult> {
  return request<RemoveSeriesResult>(withId(removeSeriesItemsEp, id), {
    body: { gallery_ids: galleryIds },
    signal,
  });
}

export interface DownloadSelectedResult {
  queued?: number;
  skipped?: number;
}

/** Queue cloud favourites for download (grouped by favcat by the caller). */
export function downloadSelectedFavorites(
  favcat: number,
  gids: number[],
  options: { quality?: "original"; archive?: boolean } = {},
  signal?: AbortSignal,
): Promise<DownloadSelectedResult> {
  return request<DownloadSelectedResult>(downloadSelectedFavoritesEp, {
    body: { favcat, gids, ...options },
    signal,
  });
}
