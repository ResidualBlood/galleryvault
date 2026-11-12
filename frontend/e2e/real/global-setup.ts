/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import { readFileSync, rmSync } from "node:fs";
import { request } from "@playwright/test";
import {
  REAL_BASE_URL,
  REAL_STORAGE_STATE,
  ensureStorageStateFile,
  requireRealPassword,
} from "./storage";

/**
 * Sign in once per run and persist cookies/CSRF for every real spec.
 *
 * The shared test environment sits behind `limit_req zone=login rate=10r/m
 * burst=5`; per-test logins produced nginx 503s in the 36-case parity run.
 * Tests call `ensureSession()` instead, which only re-authenticates when the
 * stored session has actually expired.
 */
export default async function globalSetup(): Promise<void> {
  if (!process.env.GV_E2E_PASSWORD) {
    // Keep `--list` and password-less skipped runs working; a test that really
    // needs auth fails in `ensureSession()` with the explicit env message.
    ensureStorageStateFile();
    return;
  }

  rmSync(REAL_STORAGE_STATE, { force: true });
  const api = await request.newContext({ baseURL: REAL_BASE_URL });
  try {
    const login = await api.post("/login", {
      form: { password: requireRealPassword() },
      failOnStatusCode: false,
    });
    if (!login.ok()) {
      throw new Error(`real E2E global login POST /login failed with ${login.status()}`);
    }
    const session = await api.get("/api/auth/session", { failOnStatusCode: false });
    if (!session.ok()) {
      throw new Error(`real E2E global login session check failed with ${session.status()}`);
    }
    const body = (await session.json()) as { authenticated?: boolean };
    if (!body.authenticated) {
      throw new Error("real E2E global login did not produce an authenticated session");
    }
    await api.storageState({ path: REAL_STORAGE_STATE });
  } finally {
    await api.dispose();
  }

  // CSRF is issued alongside the session cookie; fail early if it is absent so
  // mutation tests do not start with a context that cannot write.
  const state = readFileSync(REAL_STORAGE_STATE, "utf8");
  const cookies = (JSON.parse(state) as { cookies?: Array<{ name: string }> }).cookies ?? [];
  if (!cookies.some((cookie) => cookie.name === "galleryvault_csrf")) {
    throw new Error("real E2E global login did not persist the galleryvault_csrf cookie");
  }
}
