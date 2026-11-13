import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import Icons from "unplugin-icons/vite";

export default defineConfig({
  plugins: [vue(), Icons({ compiler: "vue3", scale: 1, defaultClass: "gv-icon" })],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "userscript/**/*.test.ts"],
    restoreMocks: true,
    clearMocks: true,
  },
});
