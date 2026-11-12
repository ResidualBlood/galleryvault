import { request } from "./client";
import { galleryListsEp } from "./galleries";
import {
  createListEp,
  listItemsEp,
  listsEp,
  removeListItemsEp,
} from "./library";

export interface GalleryList {
  id: number;
  name: string;
  count?: number;
  created_at?: string | null;
}

export interface GalleryListCollection {
  items: GalleryList[];
}

export interface GalleryListsForItem {
  items: Array<{ id: number; name: string }>;
}

export async function fetchLists(signal?: AbortSignal): Promise<GalleryList[]> {
  const data = await request<GalleryListCollection>(listsEp, { signal });
  return Array.isArray(data?.items) ? data.items : [];
}

export function createList(name: string, signal?: AbortSignal): Promise<GalleryList> {
  return request<GalleryList>(createListEp, { body: { name }, signal });
}

export function addListItems(
  listId: number,
  galleryIds: number[],
  signal?: AbortSignal,
): Promise<{ id: number; added: number }> {
  return request<{ id: number; added: number }>(
    { method: listItemsEp.method, path: listItemsEp.path.replace("{id}", String(listId)) },
    { body: { gallery_ids: galleryIds }, signal },
  );
}

export function removeListItems(
  listId: number,
  galleryIds: number[],
  signal?: AbortSignal,
): Promise<{ id: number; removed: number }> {
  return request<{ id: number; removed: number }>(
    { method: removeListItemsEp.method, path: removeListItemsEp.path.replace("{id}", String(listId)) },
    { body: { gallery_ids: galleryIds }, signal },
  );
}

export async function fetchGalleryLists(
  galleryId: number,
  signal?: AbortSignal,
): Promise<GalleryListsForItem["items"]> {
  const data = await request<GalleryListsForItem>(
    { method: galleryListsEp.method, path: galleryListsEp.path.replace("{id}", String(galleryId)) },
    { signal },
  );
  return Array.isArray(data?.items) ? data.items : [];
}
