/**
 * Standalone harness for the favourites / downloads / history views.
 *
 * The application route table is owned by another batch, so the e2e run mounts
 * the real views with the real Pinia stores, i18n, API client and design tokens
 * on a memory router. Screenshots therefore exercise the production components,
 * not a mock layout.
 */
import { createApp, h } from "vue";
import { createPinia } from "pinia";
import { RouterView, createMemoryHistory, createRouter } from "vue-router";
import FavoritesView from "@/views/favorites/FavoritesView.vue";
import FavListView from "@/views/favorites/FavListView.vue";
import DownloadsView from "@/views/downloads/DownloadsView.vue";
import HistoryView from "@/views/history/local/HistoryView.vue";
import Toast from "@/components/ui/Toast.vue";
import { i18n, setLocale } from "@/i18n";
import "@/styles/tokens.css";
import "@/styles/base.css";

const params = new URLSearchParams(location.search);
const view = params.get("view") ?? "favorites";
const theme = params.get("theme") === "light" ? "light" : "dark";
const defaultPath: Record<string, string> = {
  favorites: "/favorites",
  favlist: "/favorites/1",
  downloads: "/downloads",
  history: "/history",
};
const target = params.get("path") ?? defaultPath[view] ?? "/favorites";

document.documentElement.dataset.theme = theme;
setLocale("zh");

const Stub = {
  render: () => h("div", { class: "harness-stub", "data-testid": "stub-route" }),
};

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: "/favorites", name: "favorites", component: FavoritesView },
    { path: "/favorites/:id", name: "favorites-list", component: FavListView },
    { path: "/downloads", name: "downloads", component: DownloadsView },
    { path: "/history", name: "history", component: HistoryView },
    { path: "/updates", name: "updates", component: Stub },
    { path: "/gallery/:id", name: "gallery", component: Stub },
    { path: "/reader/:id/:page", name: "reader", component: Stub },
    { path: "/:pathMatch(.*)*", component: Stub },
  ],
});

await router.push(target);
await router.isReady();

const app = createApp({
  render: () =>
    h("div", { class: "harness", "data-testid": "harness" }, [h(RouterView), h(Toast)]),
});

app.use(createPinia());
app.use(i18n);
app.use(router);
app.mount("#app");
