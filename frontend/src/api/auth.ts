import { ep, request, requestForm } from "./client";

export const sessionEp = ep("GET", "/api/auth/session");
export const loginEp = ep("POST", "/login");
export const logoutEp = ep("POST", "/logout");
export const changePasswordEp = ep("POST", "/api/auth/change-password");
export const onboardingStatusEp = ep("GET", "/api/onboarding/status");

export interface CookieHealth {
  state?: string;
  message?: string;
}

export interface SessionInfo {
  authenticated: boolean;
  auth_required?: boolean;
  must_change_password?: boolean;
  cookie_health?: CookieHealth;
}

export function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>(sessionEp, { skipAuthRedirect: true });
}

export function login(password: string): Promise<unknown> {
  return requestForm(loginEp, { password }, { skipAuthRedirect: true });
}

export function logout(): Promise<unknown> {
  return requestForm(logoutEp, {}, { skipAuthRedirect: true });
}

export function changePassword(current: string, next: string): Promise<unknown> {
  return request(changePasswordEp, { body: { current, new: next } });
}

export function getOnboardingStatus(): Promise<unknown> {
  return request(onboardingStatusEp);
}
