import rawMap from "../../../parity/settings-map.json";

export type SettingStorage = "us" | "ls" | "readonly" | "env" | "none";

export type SettingControl =
  | "select"
  | "switch"
  | "text"
  | "number"
  | "textarea"
  | "secret"
  | "baseurl"
  | "online-defaults"
  | "readonly"
  | "link";

export type SettingSource = "server" | "aux" | "env" | "opds";

export interface SettingOption {
  value: string;
  labelKey: string;
}

export interface SettingField {
  key: string;
  storage: SettingStorage;
  control: SettingControl;
  labelKey: string;
  helpKey?: string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  options?: SettingOption[];
  security?: boolean;
  secret?: boolean;
  list?: boolean;
  endpoint?: string;
  source?: SettingSource;
  href?: string;
  download?: boolean;
  external?: boolean;
}

export interface SettingAction {
  id: string;
  kind: string;
  labelKey: string;
  helpKey?: string;
  to?: string;
}

export interface SettingGroup {
  id: string;
  order: number;
  titleKey: string;
  descriptionKey: string;
  fields: SettingField[];
  actions: SettingAction[];
}

interface SettingsMap {
  version: number;
  source: string;
  groups: SettingGroup[];
  notExposed: string[];
  securitySensitiveKeys: string[];
}

const map = rawMap as unknown as SettingsMap;

/** The 13 groups from PLAN §4.2, ordered as in the plan table. */
export const SETTINGS_GROUPS: readonly SettingGroup[] = [...map.groups].sort(
  (a, b) => a.order - b.order,
);

export const NOT_EXPOSED_KEYS: readonly string[] = map.notExposed;

/** Backend `_SECURITY_SENSITIVE_KEYS` (routers/settings.py:73). */
export const SECURITY_SENSITIVE_KEYS: readonly string[] = map.securitySensitiveKeys;

export const ALL_FIELDS: readonly SettingField[] = SETTINGS_GROUPS.flatMap(
  (group) => group.fields,
);

export function groupById(id: string): SettingGroup | undefined {
  return SETTINGS_GROUPS.find((group) => group.id === id);
}

export function fieldByKey(key: string): SettingField | undefined {
  return ALL_FIELDS.find((field) => field.key === key);
}

export function fieldsForGroup(id: string): readonly SettingField[] {
  return groupById(id)?.fields ?? [];
}

/** Server-persisted (`user_settings`) fields only; LS/readonly/env never POST. */
export function serverFields(group: SettingGroup): SettingField[] {
  return group.fields.filter(
    (field) => field.storage === "us" && field.endpoint !== "pause",
  );
}

export function isSecuritySensitive(field: SettingField): boolean {
  return Boolean(field.security) || SECURITY_SENSITIVE_KEYS.includes(field.key);
}

/** Flat rows used by the top search; `titleKey` keeps the result group visible. */
export interface SettingSearchHit {
  group: SettingGroup;
  field: SettingField;
}

export function searchSettings(query: string): SettingSearchHit[] {
  const term = query.trim().toLowerCase();
  if (!term) return [];
  return SETTINGS_GROUPS.flatMap((group) =>
    group.fields
      .filter((field) => {
        const haystack = `${field.key} ${field.labelKey} ${field.helpKey ?? ""} ${group.titleKey}`;
        return haystack.toLowerCase().includes(term);
      })
      .map((field) => ({ group, field })),
  );
}
