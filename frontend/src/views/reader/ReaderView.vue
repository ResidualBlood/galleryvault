<!-- gv-polish:pending -->
<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import ReaderShell from "./ReaderShell.vue";

/**
 * Route-level wrapper for `#/reader/:id/:page`. The route table is owned by the
 * scaffold/controller; this component only adapts params and navigation so the
 * reader can also be mounted standalone (unit/E2E harness) without a router.
 */
const route = useRoute();
const router = useRouter();

const galleryId = computed(() => {
  const raw = route.params.id;
  const value = Number.parseInt(String(Array.isArray(raw) ? raw[0] : raw), 10);
  return Number.isFinite(value) ? value : 0;
});

/** `page` is the legacy zero-based index used by gallery detail thumbnails. */
const page = computed(() => {
  const raw = route.params.page;
  const value = Number.parseInt(String(Array.isArray(raw) ? raw[0] : raw), 10);
  return Number.isFinite(value) && value > 0 ? value : 0;
});

const slideshow = computed(() => {
  const raw = route.query.slideshow;
  const value = Number.parseInt(String(Array.isArray(raw) ? raw[0] : raw), 10);
  return Number.isFinite(value) && value > 0 ? value : null;
});

function close(): void {
  void router.push({ name: "gallery", params: { id: galleryId.value } });
}

function next(id: number): void {
  void router.push({ name: "reader", params: { id, page: 0 } });
}

/**
 * Mirror the reader's committed page into the hash URL (`replace`, so the
 * browser back button still returns to the gallery detail instead of walking
 * page by page). A reload of `#/reader/:id/:page` resumes on that page.
 */
function onPageChange(value: number): void {
  const nextPage = Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
  if (nextPage === page.value) return;
  void router.replace({
    name: "reader",
    params: { id: galleryId.value, page: nextPage },
    query: route.query,
  });
}
</script>

<template>
  <ReaderShell
    :gallery-id="galleryId"
    :initial-page="page"
    :initial-slideshow="slideshow"
    @close="close"
    @next="next"
    @page-change="onPageChange"
  />
</template>
