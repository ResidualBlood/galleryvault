/**
 * Standalone harness for the quick-action components.
 *
 * The application card / detail / reader wrappers are owned by other batches,
 * so this harness mounts the real GalleryActions (card / detail / toolbar)
 * with the real Pinia stores, API client, i18n and design tokens.
 */
import { createApp, h } from "vue";
import { createPinia } from "pinia";
import GalleryActions from "@/components/actions/GalleryActions.vue";
import Toast from "@/components/ui/Toast.vue";
import { i18n, setLocale } from "@/i18n";
import "@/styles/tokens.css";
import "@/styles/base.css";

const params = new URLSearchParams(location.search);
const densityParam = params.get("density") ?? "card";
const density =
  densityParam === "detail" || densityParam === "toolbar" ? densityParam : "card";
const theme = params.get("theme") === "light" ? "light" : "dark";
const favorited = params.get("favorited") === "1";
const favcat = favorited ? Number(params.get("favcat") ?? "3") : null;
const gid = Number(params.get("gid") ?? "4242");
const token = params.get("token") ?? "0123456789ab";
const inLibrary = params.get("inLibrary") === "1";
const status = params.get("status");
const title = params.get("title") ?? "Harness Gallery";

document.documentElement.dataset.theme = theme;
setLocale("zh");

const app = createApp({
  render() {
    return h("div", { class: "harness", "data-testid": "harness" }, [
      h(
        "div",
        {
          class: ["gallery-card", density === "detail" ? "gallery-card--wide" : ""],
          "data-testid": "card-shell",
        },
        [
          h(GalleryActions, {
            gid,
            token,
            title,
            density,
            source: "online",
            favorited,
            favcat,
            inLibrary,
            downloadStatus: status,
            onRead: () => {
              (window as unknown as { __read?: number }).__read =
                ((window as unknown as { __read?: number }).__read ?? 0) + 1;
            },
          }),
        ],
      ),
      h(Toast),
    ]);
  },
});

app.use(createPinia());
app.use(i18n);
app.mount("#app");
