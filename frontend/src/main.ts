import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "@/App.vue";
import router from "@/router";
import { i18n } from "@/i18n";
import { setUnauthorizedHandler } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import "@/styles/tokens.css";
import "@/styles/base.css";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);

const settings = useSettingsStore();
settings.init();

const auth = useAuthStore();
setUnauthorizedHandler(() => {
  auth.markUnauthorized();
  if (router.currentRoute.value.name !== "login") {
    void router.replace({ name: "login" });
  }
});

app.use(router);
app.use(i18n);
app.mount("#app");
