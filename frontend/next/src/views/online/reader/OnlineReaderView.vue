<script setup lang="ts">
/**
 * Route-level wrapper for `#/online/g/:gid/:token/read/:page`.
 *
 * The route table is owned by the scaffold/controller and this batch must not
 * edit it, so the wrapper is deliberately thin: it adapts route params,
 * mirrors page turns back into the hash with `replace` (same behaviour as the
 * local reader) and forwards navigation events. `OnlineReaderShell` holds all
 * reader logic and can be mounted without a router for E2E.
 */
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import OnlineReaderShell from "./OnlineReaderShell.vue";

const route = useRoute();
const router = useRouter();

function param(name: string): string {
  const raw = route.params[name];
  return String(Array.isArray(raw) ? raw[0] : (raw ?? ""));
}

const gid = computed(() => {
  const value = Number.parseInt(param("gid"), 10);
  return Number.isFinite(value) && value > 0 ? value : 0;
});

const token = computed(() => param("token"));

/**
 * `0` in the URL means "no explicit page": resume the stored online progress.
 * A page > 0 (thumbnail / deep link) wins over the stored progress.
 */
const initialPage = computed<number | null>(() => {
  const value = Number.parseInt(param("page"), 10);
  return Number.isFinite(value) && value > 0 ? value : null;
});

function openDetail(): void {
  if (!gid.value || !token.value) {
    void router.push({ name: "online" });
    return;
  }
  void router.push({
    name: "online-detail",
    params: { gid: gid.value, token: token.value },
  });
}

function onPageChange(page: number): void {
  if (!gid.value || !token.value) return;
  const nextPage = Number.isFinite(page) ? Math.max(0, Math.trunc(page)) : 0;
  void router.replace({
    name: "online-reader",
    params: { gid: gid.value, token: token.value, page: nextPage },
    query: route.query,
  });
}

/* Favorite / download are performed by GalleryActions (fe-quick-actions); the
   reader only provides the toolbar slot and forwards the intents. */
function onFavorite(): void {}

function onDownload(): void {}
</script>

<template>
  <OnlineReaderShell
    v-if="gid && token"
    :gid="gid"
    :token="token"
    :initial-page="initialPage"
    @close="openDetail"
    @page-change="onPageChange"
    @favorite="onFavorite"
    @download="onDownload"
  />
  <p v-else class="online-reader-invalid" data-testid="online-reader-invalid">
    {{ $t("onlineReader.loadFailed") }}
  </p>
</template>

<style scoped>
.online-reader-invalid {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  margin: 0;
  padding: var(--gv-space-5);
  background: var(--gv-color-reader-surface);
  color: var(--gv-color-reader-on-surface);
  font: var(--gv-type-body-large);
  text-align: center;
}
</style>
