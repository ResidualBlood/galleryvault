import { listFromText } from "./preferences";
import {
  SECURITY_SENSITIVE_KEYS,
  serverFields,
  type SettingField,
  type SettingGroup,
} from "./schema";

export interface FieldError {
  key: string;
  messageKey: string;
}

export interface GroupSavePlan {
  payload: Record<string, unknown>;
  changedKeys: string[];
  requiresConfirmation: boolean;
  errors: FieldError[];
}

const BASE_URL_HOSTS = ["exhentai.org", "e-hentai.org"];

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function effectiveValue(
  field: SettingField,
  raw: unknown,
  customBaseUrl: string,
): unknown {
  switch (field.control) {
    case "switch":
      return Boolean(raw);
    case "number": {
      if (raw === "" || raw === null || raw === undefined) return null;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : raw;
    }
    case "textarea":
      return field.list ? listFromText(raw) : text(raw);
    case "text":
      if (field.list) return listFromText(raw);
      return text(raw);
    case "baseurl": {
      const chosen = text(raw);
      return chosen === "__custom__" ? text(customBaseUrl) : chosen;
    }
    case "online-defaults": {
      const value = (raw ?? {}) as { list?: unknown; tl?: unknown; min_rating?: unknown };
      return {
        list: text(value.list) || "search",
        tl: Number(value.tl) || 15,
        min_rating:
          value.min_rating === "" || value.min_rating === null || value.min_rating === undefined
            ? null
            : Number(value.min_rating),
      };
    }
    default:
      return raw;
  }
}

function sameValue(field: SettingField, left: unknown, right: unknown): boolean {
  if (field.control === "switch") return Boolean(left) === Boolean(right);
  if (field.control === "number") {
    const a = left === "" || left === null ? null : Number(left);
    const b = right === "" || right === null ? null : Number(right);
    if (a === null || b === null) return a === b;
    return Number.isFinite(a) && Number.isFinite(b) ? a === b : a === b;
  }
  if (field.control === "online-defaults") {
    return JSON.stringify(left) === JSON.stringify(right);
  }
  if ((field.control === "textarea" && field.list) || (field.control === "text" && field.list)) {
    return JSON.stringify(listFromText(left)) === JSON.stringify(listFromText(right));
  }
  return text(left) === text(right);
}

function toPayload(field: SettingField, effective: unknown): unknown {
  if (field.control === "number") return Number(effective);
  if (field.control === "switch") return Boolean(effective);
  if (field.control === "textarea" && field.list) {
    return (effective as unknown[]).map((entry) => String(entry));
  }
  if (field.control === "text" && field.list) {
    const entries = effective as string[];
    return field.key === "telegram_allowed_user_ids"
      ? entries.map((entry) => Number(entry))
      : entries;
  }
  return effective;
}

function validate(field: SettingField, effective: unknown): FieldError | null {
  if (field.control === "number") {
    const value = Number(effective);
    if (!Number.isFinite(value)) return { key: field.key, messageKey: "settings.error.number" };
    if (field.min !== undefined && value < field.min) {
      return { key: field.key, messageKey: "settings.error.range" };
    }
    if (field.max !== undefined && value > field.max) {
      return { key: field.key, messageKey: "settings.error.range" };
    }
  }
  if (field.key === "library_roots") {
    if (!Array.isArray(effective) || effective.length === 0) {
      return { key: field.key, messageKey: "settings.error.libraryRoots" };
    }
  }
  if (field.control === "baseurl") {
    const url = text(effective);
    let host = "";
    try {
      host = new URL(url).hostname.toLowerCase();
    } catch {
      return { key: field.key, messageKey: "settings.error.baseUrl" };
    }
    if (!BASE_URL_HOSTS.some((allowed) => host === allowed)) {
      return { key: field.key, messageKey: "settings.error.baseUrlHost" };
    }
  }
  return null;
}

/**
 * Diff one group against the baseline fetched from the server.
 *
 * Only this group's server-backed fields are emitted; untouched fields (and
 * fields the UI cannot read) are never sent, which is what keeps the legacy
 * "write every fallback value back" bug (inv-settings.md §I P3) from returning.
 */
export function computeGroupSave(
  group: SettingGroup,
  draft: Record<string, unknown>,
  baseline: Record<string, unknown>,
  options: { customBaseUrl?: string; baselineCustomBaseUrl?: string } = {},
): GroupSavePlan {
  const payload: Record<string, unknown> = {};
  const changedKeys: string[] = [];
  const errors: FieldError[] = [];
  const customBaseUrl = options.customBaseUrl ?? "";
  const baselineCustomBaseUrl = options.baselineCustomBaseUrl ?? "";

  for (const field of serverFields(group)) {
    if (field.control === "secret") {
      const secret = text(draft[field.key]);
      if (secret) {
        payload[field.key] = secret;
        changedKeys.push(field.key);
      }
      continue;
    }
    const current = effectiveValue(field, draft[field.key], customBaseUrl);
    const base = effectiveValue(field, baseline[field.key], baselineCustomBaseUrl);
    const fieldError = validate(field, current);
    if (fieldError) errors.push(fieldError);
    if (!sameValue(field, current, base)) {
      payload[field.key] = toPayload(field, current);
      changedKeys.push(field.key);
    }
  }

  const httpProxy = text(draft.http_proxy);
  const socksProxy = text(draft.socks5_proxy);
  if (httpProxy && socksProxy) {
    errors.push({ key: "socks5_proxy", messageKey: "settings.error.proxyConflict" });
  }

  return {
    payload,
    changedKeys,
    errors,
    requiresConfirmation: changedKeys.some((key) => SECURITY_SENSITIVE_KEYS.includes(key)),
  };
}

/** A security-sensitive change needs the current password before it is sent. */
export function canSubmit(plan: GroupSavePlan, confirmed: boolean): boolean {
  if (plan.errors.length > 0) return false;
  if (plan.changedKeys.length === 0) return false;
  return confirmed || !plan.requiresConfirmation;
}

/** Baseline (control-form) values for every field of a group. */
export function buildBaseline(
  group: SettingGroup,
  server: Record<string, unknown>,
  preferences: Record<string, unknown>,
  control: (field: SettingField, value: unknown) => unknown,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of group.fields) {
    if (field.storage === "ls") {
      out[field.key] = control(field, preferences[field.key] ?? field.default);
    } else if (field.storage === "us" && field.control !== "secret") {
      out[field.key] = control(field, server[field.key] ?? field.default);
    } else if (field.storage === "us") {
      out[field.key] = "";
    }
  }
  return out;
}
