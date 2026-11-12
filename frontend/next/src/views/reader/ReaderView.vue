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

const page = computed(() => {
  const raw = route.params.page;
  const value = Number.parseInt(String(Array.isArray(raw) ? raw[0] : raw), 10);
  return Number.isFinite(value) && value > 0 ? value - 1 : 0;
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
  void router.push({ name: "reader", params: { id, page: 1 } });
}
</script>

<template>
  <ReaderShell
    :gallery-id="galleryId"
    :initial-page="page"
    :initial-slideshow="slideshow"
    @close="close"
    @next="next"
  />
</template>
