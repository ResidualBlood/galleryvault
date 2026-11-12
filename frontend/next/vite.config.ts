import { fileURLToPath, URL } from "node:url";
import { existsSync } from "node:fs";
import { defineConfig, loadEnv, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";
import { VitePWA } from "vite-plugin-pwa";

const projectRoot = fileURLToPath(new URL("./", import.meta.url));

/**
 * The PWA stays in its own entry module so the app shell does not import it
 * (and so the service worker is never registered during `vite dev`). The
 * manifest is a static file in public/, so only the link is injected here.
 */
function pwaHtmlLink(): Plugin {
  return {
    name: "gv-pwa-html-link",
    transformIndexHtml(html) {
      return {
        html,
        tags: [
          {
            tag: "link",
            attrs: { rel: "manifest", href: "/manifest.webmanifest" },
            injectTo: "head",
          },
        ],
      };
    },
  };
}

/**
 * `src/pwa/init.ts` is a second Rollup input. Once the bundle exists, point
 * index.html at the hashed chunk (and its extracted CSS); doing this in
 * generateBundle is what makes Vite treat it as a real entry instead of an
 * unbundled `/src/...` URL.
 */
function pwaEntryScript(): Plugin {
  return {
    name: "gv-pwa-entry-script",
    enforce: "post",
    generateBundle(_options, bundle) {
      const chunk = Object.values(bundle).find(
        (item) => item.type === "chunk" && item.facadeModuleId?.endsWith("/src/pwa/init.ts"),
      );
      const html = bundle["index.html"];
      if (!chunk || chunk.type !== "chunk" || !html || html.type !== "asset") return;

      const tags: string[] = [];
      for (const css of chunk.viteMetadata?.importedCss ?? []) {
        tags.push(`<link rel="stylesheet" crossorigin href="/${css}">`);
      }
      tags.push(`<script type="module" crossorigin src="/${chunk.fileName}"></script>`);
      html.source = String(html.source).replace("</body>", `${tags.join("")}</body>`);
    },
  };
}

/**
 * `src/views/settings/schema.ts` imports the parity map. The production image
 * excludes `parity/` (test artifacts), so fall back to the copy under
 * `src/pwa/` only when the real file is absent (i.e. inside `docker build`).
 */
function settingsMapFallback(): Plugin {
  const original = fileURLToPath(new URL("./parity/settings-map.json", import.meta.url));
  const fallback = fileURLToPath(
    new URL("./src/pwa/settings-map.fallback.json", import.meta.url),
  );
  return {
    name: "gv-settings-map-fallback",
    enforce: "pre",
    resolveId(source) {
      if (!source.endsWith("parity/settings-map.json")) return null;
      return existsSync(original) ? null : fallback;
    },
  };
}

export default defineConfig(({ mode }) => {
  // Development-only bridge to the FastAPI backend.
  // Production serves the built SPA and proxies the same paths from nginx.
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
      settingsMapFallback(),
      vue(),
      VueI18nPlugin({
        include: [fileURLToPath(new URL("./src/locales/**", import.meta.url))],
        runtimeOnly: true,
        compositionOnly: true,
        strictMessage: false,
        escapeHtml: false,
      }),
      VitePWA({
        strategies: "injectManifest",
        srcDir: "src/pwa",
        filename: "sw.ts",
        // /sw.js is registered by src/pwa/register.ts, and the manifest link is
        // injected by pwaHtmlLink(); both keep index.html under our control.
        injectRegister: false,
        registerType: "prompt",
        manifest: false,
        injectManifest: {
          globPatterns: ["**/*.{js,mjs,css,html,svg,png,webmanifest,woff2}"],
          globIgnores: ["sw.js", "workbox-*.js", "galleryvault-companion.user.js"],
        },
        devOptions: { enabled: false },
      }),
      pwaHtmlLink(),
      pwaEntryScript(),
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
    build: {
      rollupOptions: {
        input: {
          main: fileURLToPath(new URL("./index.html", import.meta.url)),
          "pwa-init": fileURLToPath(new URL("./src/pwa/init.ts", import.meta.url)),
        },
      },
    },
  };
});
