/**
 * Standalone online-browse harness for mock E2E.
 *
 * The application route table is owned by the scaffold/controller and is
 * outside this batch's scope, so the real list/detail views are mounted on a
 * throw-away hash router here. URLs keep the production shape
 * (`#/online`, `#/online/g/:gid/:token`, `#/online/g/:gid/:token/read/:page`)
 * so navigation and browser-back behaviour match the final app.
 */
import { createApp, h } from "vue";
import { createPinia } from "pinia";
import {
  createRouter,
  createWebHashHistory,
  RouterView,
  useRoute,
} from "vue-router";
import AppShell from "@/components/AppShell.vue";
import { i18n } from "@/i18n";
import { useSettingsStore } from "@/stores/settings";
import OnlineListView from "@/views/online/list/OnlineListView.vue";
import OnlineDetailView from "@/views/online/detail/OnlineDetailView.vue";
import "@/styles/tokens.css";
import "@/styles/base.css";

const params = new URLSearchParams(location.search);
const theme = params.get("theme");
const lang = params.get("lang");
if (theme === "light" || theme === "dark" || theme === "system") {
  localStorage.setItem("gv_theme", theme);
}
if (lang === "en" || lang === "zh") {
  localStorage.setItem("gv_lang", lang);
}

const Stub = {
  name: "HarnessStub",
  setup() {
    const route = useRoute();
    return () =>
      h("div", { "data-testid": "harness-stub", "data-route": String(route.name) }, [
        h("h1", route.name === "online-reader" ? "Online reader stub" : "Harness stub"),
      ]);
  },
};

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", redirect: "/online" },
        {
          path: "online",
          name: "online",
          component: OnlineListView,
          meta: { title: "app.nav.online" },
        },
        {
          path: "online/g/:gid/:token",
          name: "online-detail",
          component: OnlineDetailView,
          meta: { title: "app.nav.online" },
        },
        {
          path: "online/g/:gid/:token/read/:page",
          name: "online-reader",
          component: Stub,
          meta: { title: "app.nav.online" },
        },
        {
          path: "settings",
          name: "settings",
          component: Stub,
          meta: { title: "app.nav.settings" },
        },
        {
          path: "gallery/:id",
          name: "gallery",
          component: Stub,
          meta: { title: "app.nav.library" },
        },
        { path: ":pathMatch(.*)*", redirect: "/online" },
      ],
    },
  ],
});

const app = createApp({ render: () => h(RouterView) });
const pinia = createPinia();
app.use(pinia);
useSettingsStore().init();
app.use(router);
app.use(i18n);
app.mount("#app");
