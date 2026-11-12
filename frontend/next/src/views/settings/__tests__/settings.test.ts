import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { i18n } from "@/i18n";
import SettingsGroupPanel from "@/views/settings/SettingsGroupPanel.vue";
import { ensureSettingsMessages } from "@/views/settings/messages";
import {
  NOT_EXPOSED_KEYS,
  SETTINGS_GROUPS,
  fieldByKey,
  groupById,
  searchSettings,
} from "@/views/settings/schema";
import { buildBaseline, canSubmit, computeGroupSave } from "@/views/settings/save";
import { controlValue } from "@/views/settings/preferences";
import zhSettings from "@/locales/zh/settings.json";
import enSettings from "@/locales/en/settings.json";
import getFixture from "../../../../e2e/fixtures/settings-sys/settings-get.json";
import legacyKeys from "../../../../e2e/fixtures/settings-sys/legacy-settings-keys.json";

ensureSettingsMessages();
i18n.global.locale.value = "zh";

type Tree = Record<string, unknown>;

function lookup(tree: Tree, path: string): unknown {
  return path.split(".").reduce<unknown>((node, part) => {
    if (!node || typeof node !== "object") return undefined;
    return (node as Tree)[part];
  }, tree);
}

function hasKey(tree: Tree, key: string): boolean {
  const path = key.startsWith("settings.") ? key.slice("settings.".length) : key;
  return typeof lookup(tree, path) === "string";
}

function baselineFor(groupId: string): Record<string, unknown> {
  const group = groupById(groupId);
  if (!group) throw new Error(`missing group ${groupId}`);
  return buildBaseline(group, getFixture as Tree, {}, controlValue);
}

function planFor(groupId: string, patch: Record<string, unknown>, custom = "") {
  const group = groupById(groupId);
  if (!group) throw new Error(`missing group ${groupId}`);
  const baseline = baselineFor(groupId);
  const draft = { ...baseline, ...patch };
  return computeGroupSave(group, draft, baseline, { customBaseUrl: custom });
}

describe("settings map", () => {
  it("has the 13 PLAN §4.2 groups in order", () => {
    expect(SETTINGS_GROUPS).toHaveLength(13);
    expect(SETTINGS_GROUPS.map((group) => group.id)).toEqual([
      "appearance",
      "reader",
      "network",
      "online",
      "library",
      "download",
      "favorites",
      "archive",
      "tags",
      "notifications",
      "account",
      "integrations",
      "system",
    ]);
    expect(SETTINGS_GROUPS.map((group) => group.order)).toEqual(
      Array.from({ length: 13 }, (_, index) => index + 1),
    );
  });

  it("maps every old settings page persisted key (37) to a group", () => {
    expect(legacyKeys).toHaveLength(37);
    for (const key of legacyKeys) {
      const field = fieldByKey(key);
      expect(field, `${key} is missing from settings-map.json`).toBeTruthy();
      expect(field?.storage, key).toBe("us");
    }
  });

  it("maps every GET /api/settings key or lists it as intentionally hidden", () => {
    for (const key of Object.keys(getFixture)) {
      const field = fieldByKey(key);
      expect(
        Boolean(field) || NOT_EXPOSED_KEYS.includes(key),
        `${key} is neither rendered nor in notExposed`,
      ).toBe(true);
    }
  });

  it("keeps every label/option/help key translated in zh and en", () => {
    const zh = zhSettings as unknown as Tree;
    const en = enSettings as unknown as Tree;
    for (const group of SETTINGS_GROUPS) {
      expect(hasKey(zh, group.titleKey), group.titleKey).toBe(true);
      expect(hasKey(en, group.titleKey), group.titleKey).toBe(true);
      expect(hasKey(zh, group.descriptionKey), group.descriptionKey).toBe(true);
      expect(hasKey(en, group.descriptionKey), group.descriptionKey).toBe(true);
      for (const field of group.fields) {
        expect(hasKey(zh, field.labelKey), field.labelKey).toBe(true);
        expect(hasKey(en, field.labelKey), field.labelKey).toBe(true);
        if (field.helpKey) {
          expect(hasKey(zh, field.helpKey), field.helpKey).toBe(true);
          expect(hasKey(en, field.helpKey), field.helpKey).toBe(true);
        }
        for (const option of field.options ?? []) {
          expect(hasKey(zh, option.labelKey), option.labelKey).toBe(true);
          expect(hasKey(en, option.labelKey), option.labelKey).toBe(true);
        }
      }
      for (const action of group.actions) {
        expect(hasKey(zh, action.labelKey), action.labelKey).toBe(true);
        expect(hasKey(en, action.labelKey), action.labelKey).toBe(true);
      }
    }
  });

  it("renders every mapped key inside its group", () => {
    for (const group of SETTINGS_GROUPS) {
      const values: Record<string, unknown> = {};
      for (const field of group.fields) {
        values[field.key] =
          field.control === "switch"
            ? false
            : field.control === "online-defaults"
              ? { list: "search", tl: "15", min_rating: "" }
              : field.control === "select" || field.control === "baseurl"
                ? (field.options?.[0]?.value ?? "")
                : "";
      }
      const wrapper = mount(SettingsGroupPanel, {
        props: { group, values },
        global: { plugins: [i18n] },
      });
      const rendered = wrapper
        .findAll("[data-setting-key]")
        .map((row) => row.attributes("data-setting-key"));
      expect(rendered).toEqual(group.fields.map((field) => field.key));
      wrapper.unmount();
    }
  });

  it("searches by key and shows which group owns the hit", () => {
    const hits = searchSettings("socks5_proxy");
    expect(hits.map((hit) => hit.field.key)).toContain("socks5_proxy");
    expect(hits[0]?.group.id).toBe("network");
    expect(searchSettings("tag_translation").map((hit) => hit.field.key)).toContain(
      "tag_translation_update_interval_minutes",
    );
  });
});

describe("per-group save diff", () => {
  it("submits only the changed key of the active group", () => {
    const plan = planFor("download", { download_concurrency: "8" });
    expect(plan.payload).toEqual({ download_concurrency: 8 });
    expect(plan.changedKeys).toEqual(["download_concurrency"]);
  });

  it("never writes fallback values for untouched keys the UI does not read", () => {
    expect(planFor("tags", {}).changedKeys).toEqual([]);
    const plan = planFor("tags", { tag_translation_update_interval_minutes: "60" });
    expect(plan.payload).toEqual({ tag_translation_update_interval_minutes: 60 });
    expect(planFor("download", {}).payload).toEqual({});
  });

  it("ignores localStorage fields when diffing server payloads", () => {
    const plan = planFor("appearance", {
      gv_theme: "light",
      title_display: "english",
    });
    expect(plan.payload).toEqual({ title_display: "english" });
  });

  it("sends write-only secrets only when a new value is typed", () => {
    expect(planFor("notifications", { telegram_bot_token: "" }).payload).toEqual({});
    const plan = planFor("notifications", { telegram_bot_token: "123:abc" });
    expect(plan.payload).toEqual({ telegram_bot_token: "123:abc" });
    expect(plan.changedKeys).toEqual(["telegram_bot_token"]);
  });

  it("keeps http_proxy and socks5_proxy mutually exclusive", () => {
    const plan = planFor("network", {
      http_proxy: "http://127.0.0.1:8080",
      socks5_proxy: "socks5://127.0.0.1:1080",
    });
    expect(plan.errors.map((error) => error.messageKey)).toContain(
      "settings.error.proxyConflict",
    );
    expect(canSubmit(plan, true)).toBe(false);
  });

  it("blocks security-sensitive keys until the password is confirmed", () => {
    const plan = planFor("download", { download_root: "/srv/new-downloads" });
    expect(plan.requiresConfirmation).toBe(true);
    expect(canSubmit(plan, false)).toBe(false);
    expect(canSubmit(plan, true)).toBe(true);
    expect(plan.payload).toEqual({ download_root: "/srv/new-downloads" });
  });

  it("accepts a custom E-Hentai base URL only on the two allowed hosts", () => {
    const allowed = computeGroupSave(
      groupById("network")!,
      { ...baselineFor("network"), exhentai_base_url: "__custom__" },
      baselineFor("network"),
      { customBaseUrl: "https://e-hentai.org" },
    );
    expect(allowed.payload).toEqual({ exhentai_base_url: "https://e-hentai.org" });

    const rejected = computeGroupSave(
      groupById("network")!,
      { ...baselineFor("network"), exhentai_base_url: "__custom__" },
      baselineFor("network"),
      { customBaseUrl: "https://example.com" },
    );
    expect(rejected.errors.map((error) => error.messageKey)).toContain(
      "settings.error.baseUrlHost",
    );
    expect(canSubmit(rejected, true)).toBe(false);
  });
});
