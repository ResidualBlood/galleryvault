/**
 * Standalone reader harness for mock E2E.
 *
 * The application route table is owned by the scaffold/controller and must not
 * be edited by this batch, so the reader is mounted directly here. It still
 * uses the real ReaderShell, API client, page source, settings persistence and
 * design tokens; only the router wrapper is skipped.
 */
import { createApp, h } from "vue";
import ReaderShell from "@/views/reader/ReaderShell.vue";
import { i18n, setLocale } from "@/i18n";
import type { ReaderFit, ReaderMode } from "@/reader/pure";
import "@/styles/tokens.css";
import "@/styles/base.css";

const params = new URLSearchParams(location.search);
const number = (key: string, fallback: number): number => {
  const parsed = Number.parseInt(params.get(key) ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const galleryId = number("id", 7);
const initialPage = Math.max(0, number("page", 0));
const total = Math.max(0, number("total", 12));
const mode = (params.get("mode") ?? "ltr") as ReaderMode;
const fit = (params.get("fit") ?? "height") as ReaderFit;
/*
 * Theme precedence: explicit `?theme=` (reader specs) → persisted `gv_theme`
 * (polish shotMatrix) → dark. `shotMatrix` can only vary the persisted key, so
 * the harness has to honour it for four-variant screenshots.
 */
const storedTheme = (() => {
  try {
    return localStorage.getItem("gv_theme");
  } catch {
    return null;
  }
})();
const theme = params.get("theme") ?? (storedTheme === "light" ? "light" : "dark");
const lang = params.get("lang") === "en" ? "en" : "zh";
const slideshow = number("slideshow", 0);
/*
 * `?meta=1` drops the page count so ReaderShell has to await
 * `GET /api/galleries/{id}` — the only way to hold the loading state still for
 * a screenshot (pageCount short-circuits the request).
 */
const pageCount = params.get("meta") === "1" ? null : total;
const title = params.get("title") ?? "Harness Gallery";

document.documentElement.dataset.theme = theme;
setLocale(lang);

interface HarnessState {
  next?: number;
  closed?: boolean;
}
declare global {
  interface Window {
    __readerHarness?: HarnessState;
  }
}
window.__readerHarness = {};

const state = window.__readerHarness;
const app = createApp({
  render: () =>
    h(ReaderShell, {
      galleryId,
      initialPage,
      initialMode: mode,
      initialFit: fit,
      initialSlideshow: slideshow > 0 ? slideshow : null,
      pageCount,
      title,
      onNext: (id: number) => {
        state.next = id;
      },
      onClose: () => {
        state.closed = true;
      },
    }),
});

app.use(i18n);
app.mount("#app");
