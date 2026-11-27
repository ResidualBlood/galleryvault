import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * One authenticated storage state for the whole real suite.
 *
 * nginx limits `POST /login` to 10r/m (burst 5); logging in once per test made
 * the 36-case parity run trip 503s from case 17 onwards. `global-setup.ts`
 * writes this file before the workers start and every browser context reuses
 * it. The file lives under the gitignored `test-results/` directory.
 */
export const REAL_BASE_URL = process.env.GV_E2E_BASE || "http://127.0.0.1:8200/";

export const REAL_STORAGE_STATE =
  process.env.GV_E2E_STORAGE_STATE ||
  fileURLToPath(new URL("../../test-results/real-auth-state.json", import.meta.url));

export function requireRealPassword(): string {
  const password = process.env.GV_E2E_PASSWORD;
  if (!password) {
    throw new Error(
      "GV_E2E_PASSWORD is required for real parity E2E (it is never read from a file or committed)",
    );
  }
  return password;
}

/** Empty state keeps `storageState` loadable for `--list` / skipped runs. */
export function ensureStorageStateFile(): void {
  mkdirSync(dirname(REAL_STORAGE_STATE), { recursive: true });
  if (!existsSync(REAL_STORAGE_STATE)) {
    writeFileSync(REAL_STORAGE_STATE, JSON.stringify({ cookies: [], origins: [] }));
  }
}
