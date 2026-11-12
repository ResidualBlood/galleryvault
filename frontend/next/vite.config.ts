import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";

const projectRoot = fileURLToPath(new URL("./", import.meta.url));

/**
 * Development-only bridge to the FastAPI backend.
 * Production serves the built SPA and proxies the same paths from nginx.
 */
export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, projectRoot, ""), ...process.env };
  const backend = env.GV_BACKEND || "http://127.0.0.1:8201";
  const proxy = {
    "/api": { target: backend, changeOrigin: false },
    "/login": { target: backend, changeOrigin: false },
    "/logout": { target: backend, changeOrigin: false },
  };

  return {
    base: "/",
    plugins: [
      vue(),
      VueI18nPlugin({
        include: [fileURLToPath(new URL("./src/locales/**", import.meta.url))],
        runtimeOnly: true,
        compositionOnly: true,
        strictMessage: false,
        escapeHtml: false,
      }),
    ],
    define: {
      __VUE_I18N_FULL_INSTALL__: true,
      __VUE_I18N_LEGACY_API__: false,
      __INTLIFY_PROD_DEVTOOLS__: false,
      __INTLIFY_DROP_MESSAGE_COMPILER__: true,
    },
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      host: "127.0.0.1",
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      proxy,
    },
  };
});
