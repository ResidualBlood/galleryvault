/**
 * Standalone harness for the maintenance views.
 *
 * The application routes are wired by the integration batch, so this fixture
 * mounts the real views with the real router / Pinia / i18n / design tokens.
 * The route names and paths mirror `src/router/routes.ts`.
 */
import { createApp, h } from "vue";
import { createPinia } from "pinia";
import { RouterView, createRouter, createWebHashHistory } from "vue-router";
import { i18n, setLocale } from "@/i18n";
import Toast from "@/components/ui/Toast.vue";
import UpdatesView from "@/views/updates/UpdatesView.vue";
import UpdatesIgnoredView from "@/views/updates/UpdatesIgnoredView.vue";
import DuplicatesView from "@/views/duplicates/DuplicatesView.vue";
import FavoriteDuplicatesView from "@/views/duplicates/FavoriteDuplicatesView.vue";
import FavoriteDuplicatesIgnoredView from "@/views/duplicates/FavoriteDuplicatesIgnoredView.vue";
import CrossGidView from "@/views/duplicates/CrossGidView.vue";
import RecycleView from "@/views/recycle/RecycleView.vue";
import IntegrityView from "@/views/integrity/IntegrityView.vue";
import "@/styles/tokens.css";
import "@/styles/base.css";

const params = new URLSearchParams(location.search);
document.documentElement.dataset.theme =
  params.get("theme") === "light" ? "light" : "dark";
setLocale(params.get("lang") === "en" ? "en" : "zh");

const Stub = { render: () => h("div", { "data-testid": "stub" }) };

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/updates", name: "updates", component: UpdatesView },
    {
      path: "/updates/ignored",
      name: "updates-ignored",
      component: UpdatesIgnoredView,
    },
    { path: "/duplicates", name: "duplicates", component: DuplicatesView },
    {
      path: "/duplicates/favorites",
      alias: ["/favorites/manage"],
      name: "favorites-manage",
      component: FavoriteDuplicatesView,
    },
    {
      path: "/favorites/ignored",
      name: "favorites-ignored",
      component: FavoriteDuplicatesIgnoredView,
    },
    {
      path: "/duplicates/cross-gid",
      name: "duplicates-cross-gid",
      component: CrossGidView,
    },
    { path: "/recycle", name: "recycle", component: RecycleView },
    { path: "/integrity", name: "integrity", component: IntegrityView },
    { path: "/gallery/:id", name: "gallery", component: Stub },
    { path: "/favorites/:id", name: "favorites-list", component: Stub },
    { path: "/archive", name: "archive", component: Stub },
    { path: "/:pathMatch(.*)*", redirect: "/updates" },
  ],
});

const app = createApp({
  render: () => h("div", { class: "harness", "data-testid": "harness" }, [h(RouterView), h(Toast)]),
});

app.use(createPinia());
app.use(i18n);
app.use(router);
app.mount("#app");

void router.isReady();
