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
const theme = params.get("theme") ?? "dark";
const lang = params.get("lang") === "en" ? "en" : "zh";
const slideshow = number("slideshow", 0);
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
      pageCount: total,
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
