/**
 * Standalone harness for the online reader E2E suite.
 *
 * The route table is owned by the scaffold/controller (this batch must not edit
 * it), so `OnlineReaderShell` is mounted directly. The component itself is the
 * real one: real PageSource, real progress writer, real design tokens. Only the
 * route wrapper is skipped.
 *
 * `?view=continue` mounts the "continue reading online" section instead.
 */
import { createApp, h } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import { createPinia } from "pinia";
import OnlineReaderShell from "@/views/online/reader/OnlineReaderShell.vue";
import OnlineContinue from "@/views/history/online/OnlineContinue.vue";
import { i18n, setLocale } from "@/i18n";
import { writeOnlineImageMode, isOnlineImageMode } from "@/reader/sources";
import { READER_GID, READER_TOKEN } from "./data";
import "@/styles/tokens.css";
import "@/styles/base.css";

const params = new URLSearchParams(location.search);
const number = (key: string, fallback: number): number => {
  const parsed = Number.parseInt(params.get(key) ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const view = params.get("view") === "continue" ? "continue" : "reader";
const theme = params.get("theme") === "light" ? "light" : "dark";
const lang = params.get("lang") === "en" ? "en" : "zh";
const gid = number("gid", READER_GID);
const token = params.get("token") ?? READER_TOKEN;
const explicitPage = params.has("page") ? number("page", 0) : null;

document.documentElement.dataset.theme = theme;
setLocale(lang);

try {
  localStorage.setItem("gv_reader_mode", params.get("mode") ?? "ltr");
  localStorage.setItem("gv_reader_fit", "height");
  const imageMode = params.get("imageMode");
  localStorage.removeItem("gv_online_image_mode");
  if (imageMode && isOnlineImageMode(imageMode)) writeOnlineImageMode(imageMode);
} catch {
  /* storage disabled in a sandboxed run: defaults still work */
}

interface HarnessState {
  close?: boolean;
  page?: number;
}
declare global {
  interface Window {
    __onlineReaderHarness?: HarnessState;
  }
}
const state: HarnessState = {};
window.__onlineReaderHarness = state;

const app = createApp({
  render: () => {
    if (view === "continue") return h(OnlineContinue);
    return h(OnlineReaderShell, {
      gid,
      token,
      initialPage: explicitPage,
      onClose: () => {
        state.close = true;
      },
      onPageChange: (page: number) => {
        state.page = page;
      },
    });
  },
});

if (view === "continue") {
  const router = createRouter({
    history: createWebHashHistory(),
    routes: [
      { path: "/", name: "home", component: { render: () => null } },
      {
        path: "/online/g/:gid/:token/read/:page",
        name: "online-reader",
        component: { render: () => null },
      },
    ],
  });
  app.use(router);
}

app.use(createPinia());
app.use(i18n);
app.mount("#app");
