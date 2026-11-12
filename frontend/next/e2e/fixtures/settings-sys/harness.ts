import { createApp, h, type Component } from "vue";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { i18n, setLocale, type Lang } from "@/i18n";
import "@/styles/tokens.css";
import "@/styles/base.css";
import SettingsView from "@/views/settings/SettingsView.vue";
import WelcomeView from "@/views/welcome/WelcomeView.vue";
import LogsView from "@/views/logs/LogsView.vue";
import ArchiveView from "@/views/archive/ArchiveView.vue";
import NotificationPanel from "@/components/system/NotificationPanel.vue";
import CookieHealthBanner from "@/components/system/CookieHealthBanner.vue";
import GlobalControls from "@/components/system/GlobalControls.vue";
import ArchiveDialog from "@/components/system/ArchiveDialog.vue";

declare global {
  interface Window {
    __GV_ARCHIVE_CONFIRM__?: unknown;
  }
}

const params = new URLSearchParams(window.location.search);
const view = params.get("view") ?? "settings";
const theme = params.get("theme") === "light" ? "light" : "dark";
const lang = params.get("lang") === "en" ? "en" : "zh";
const quality = params.get("quality") === "original" ? "original" : "resample";

try {
  localStorage.setItem("gv_theme", theme);
} catch {
  /* blocked storage does not matter for the harness */
}
document.documentElement.dataset.theme = theme;
setLocale(lang as Lang);
i18n.global.locale.value = lang as Lang;

const Stub = { template: '<div data-testid="stub-page">stub</div>' };
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: "/", redirect: "/browse" },
    { path: "/browse", name: "browse", component: Stub },
    { path: "/login", name: "login", component: Stub },
    { path: "/settings", name: "settings", component: Stub },
  ],
});
router.afterEach((to) => {
  document.body.dataset.route = String(to.name ?? "");
});
void router.push("/settings");

const wrappers: Record<string, () => Component> = {
  settings: () => SettingsView,
  welcome: () => WelcomeView,
  logs: () => LogsView,
  archive: () => ArchiveView,
  notifications: () => ({
    render: () => h("div", { class: "harness" }, [h(NotificationPanel, { pollMs: 0 })]),
  }),
  "cookie-banner": () => ({
    render: () => h("div", { class: "harness" }, [h(CookieHealthBanner)]),
  }),
  "global-controls": () => ({
    render: () => h("div", { class: "harness" }, [h(GlobalControls)]),
  }),
  "archive-dialog": () => ({
    render: () =>
      h("div", { class: "harness" }, [
        h(ArchiveDialog, {
          open: true,
          gids: [101, 102],
          defaultQuality: quality,
          onClose: () => undefined,
          onConfirm: (payload: unknown) => {
            window.__GV_ARCHIVE_CONFIRM__ = payload;
          },
        }),
      ]),
  }),
};

const make = wrappers[view] ?? wrappers.settings;
const app = createApp(make());
app.use(createPinia());
app.use(router);
app.use(i18n);
app.mount("#app");
