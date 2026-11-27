import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const LOCALES = join(HERE, "..", "locales");
const LANGS = ["zh", "en"] as const;

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

function readJson(path: string): Json {
  return JSON.parse(readFileSync(path, "utf8")) as Json;
}

function leafKeys(value: Json, prefix = "", out: Set<string> = new Set()): Set<string> {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      leafKeys(child, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out.add(prefix);
  }
  return out;
}

function featureFiles(): string[] {
  return readdirSync(join(LOCALES, "zh"))
    .filter((name) => name.endsWith(".json"))
    .sort();
}

describe("locale key sets", () => {
  it("zh and en expose identical files and leaf key sets", () => {
    const zhFiles = featureFiles();
    const enFiles = readdirSync(join(LOCALES, "en"))
      .filter((name) => name.endsWith(".json"))
      .sort();
    expect(enFiles).toEqual(zhFiles);

    for (const file of zhFiles) {
      const zh = leafKeys(readJson(join(LOCALES, "zh", file)));
      const en = leafKeys(readJson(join(LOCALES, "en", file)));
      expect([...en].sort(), `${file} key-set mismatch`).toEqual([...zh].sort());
    }
  });

  it("legacy conversion keeps 763 leaves per language with no dotted keys", () => {
    for (const lang of LANGS) {
      const legacy = readJson(join(LOCALES, lang, "legacy.json"));
      const keys = leafKeys(legacy);
      expect(keys.size, `${lang} legacy leaf count`).toBe(763);
      // `ns.*` / `groups.*` are intentionally nested objects; every *flat*
      // legacy key must have been converted from dots to underscores.
      for (const key of Object.keys(legacy as Record<string, Json>)) {
        if (key === "ns" || key === "groups") continue;
        expect(key.includes("."), `${lang} legacy key "${key}" still contains a dot`).toBe(false);
      }
    }
  });

  it("keeps the same top-level legacy key order for zh and en", () => {
    const zh = readJson(join(LOCALES, "zh", "legacy.json")) as Record<string, Json>;
    const en = readJson(join(LOCALES, "en", "legacy.json")) as Record<string, Json>;
    expect(Object.keys(en)).toEqual(Object.keys(zh));
  });
});
