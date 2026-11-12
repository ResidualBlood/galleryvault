/**
 * Vitest config for the companion userscript tests.
 *
 * The project root config only collects `src/**\/*.test.ts`; the userscript
 * lives outside `src/` (it is not part of the app bundle) and this batch's
 * scope forbids touching the root config, so run:
 *
 *   npx vitest run --config userscript/vitest.config.mjs
 *
 * Follow-up for the integrator: add "userscript/**\/*.test.ts" to
 * `test.include` in frontend/next/vitest.config.ts so
 * `npm run test:unit -- userscript` picks these up as well.
 */

/* global URL */
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  root: fileURLToPath(new URL("..", import.meta.url)),
  test: {
    environment: "jsdom",
    include: ["userscript/**/*.test.ts"],
    restoreMocks: true,
    clearMocks: true,
  },
});
