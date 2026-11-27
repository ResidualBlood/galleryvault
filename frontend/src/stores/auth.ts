import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { getSession, login as loginRequest, logout as logoutRequest, type SessionInfo } from "@/api/auth";

/**
 * Authentication state. The backend is the source of truth: `init()` probes
 * `/api/auth/session`, and a 401 anywhere in the client calls markUnauthorized()
 * from the handler registered in main.ts.
 */
export const useAuthStore = defineStore("auth", () => {
  const authenticated = ref(false);
  const ready = ref(false);
  const session = ref<SessionInfo | null>(null);
  const error = ref<string | null>(null);
  const pending = ref(false);

  const mustChangePassword = computed(() => Boolean(session.value?.must_change_password));

  function applySession(value: SessionInfo | null): void {
    session.value = value;
    authenticated.value = value?.authenticated === true;
    error.value = null;
  }

  async function init(): Promise<void> {
    if (ready.value) return;
    try {
      applySession(await getSession());
    } catch {
      applySession(null);
    } finally {
      ready.value = true;
    }
  }

  async function refresh(): Promise<boolean> {
    try {
      applySession(await getSession());
    } catch {
      applySession(null);
    }
    return authenticated.value;
  }

  async function login(password: string): Promise<boolean> {
    pending.value = true;
    error.value = null;
    try {
      await loginRequest(password);
      const ok = await refresh();
      if (!ok) error.value = "login.error";
      return ok;
    } catch {
      error.value = "login.error";
      return false;
    } finally {
      pending.value = false;
    }
  }

  async function logout(): Promise<void> {
    try {
      await logoutRequest();
    } catch {
      /* cookie may already be gone; clearing local state is still correct */
    }
    applySession(null);
  }

  function markUnauthorized(): void {
    applySession(null);
    ready.value = true;
  }

  return {
    authenticated,
    ready,
    session,
    error,
    pending,
    mustChangePassword,
    init,
    refresh,
    login,
    logout,
    markUnauthorized,
  };
});
