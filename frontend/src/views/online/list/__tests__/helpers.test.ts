import { describe, expect, it } from "vitest";
import {
  ONLINE_TABLE_COLUMNS,
  appendEhTagQuery,
  languageLabel,
  languageTag,
  normalizePosted,
  splitEhQuery,
  withoutLanguageTags,
} from "../helpers";

const tags = [
  { namespace: "female", name: "big breasts", display: "巨乳" },
  { namespace: "language", name: "chinese", display: "中文" },
  { namespace: "artist", name: "fixture-artist", display: "夹具画师" },
];

describe("language inference", () => {
  it("finds the language:* tag and localises its label", () => {
    expect(languageTag(tags)?.name).toBe("chinese");
    expect(languageLabel(tags, "zh")).toBe("中文");
    expect(languageLabel(tags, "en")).toBe("chinese");
  });

  it("returns nothing when the row has no language tag", () => {
    expect(languageTag([{ namespace: "female", name: "heroine" }])).toBeNull();
    expect(languageLabel([], "zh")).toBe("");
    expect(languageLabel(null, "zh")).toBe("");
  });

  it("drops language from the inline row and table chips", () => {
    expect(withoutLanguageTags(tags).map((tag) => tag.name)).toEqual([
      "big breasts",
      "fixture-artist",
    ]);
  });
});

describe("online tag query", () => {
  it("appends the exact ns:\"name$\" token with a space", () => {
    expect(appendEhTagQuery("", { namespace: "female", name: "big breasts" })).toBe(
      'female:"big breasts$"',
    );
    expect(
      appendEhTagQuery('female:"big breasts$"', { namespace: "artist", name: "fixture-artist" }),
    ).toBe('female:"big breasts$" artist:fixture-artist$');
  });

  it("is idempotent so repeated clicks cannot duplicate a tag", () => {
    const once = appendEhTagQuery("", { namespace: "female", name: "big breasts" });
    const twice = appendEhTagQuery(once, { namespace: "female", name: "big breasts" });
    expect(twice).toBe(once);
    expect(splitEhQuery(twice)).toEqual(['female:"big breasts$"']);
  });

  it("normalises an already prefixed / quoted / dollar-suffixed tag", () => {
    const token = appendEhTagQuery("", {
      namespace: "female",
      name: 'female:"big breasts$"',
    });
    expect(token).toBe('female:"big breasts$"');
  });

  it("keeps existing non-tag keywords and quoted bodies intact", () => {
    expect(splitEhQuery('pokemon female:"big breasts$"')).toEqual([
      "pokemon",
      'female:"big breasts$"',
    ]);
    expect(
      appendEhTagQuery('pokemon female:"big breasts$"', { namespace: "artist", name: "foo bar" }),
    ).toBe('pokemon female:"big breasts$" artist:"foo bar$"');
  });
});

describe("online table columns", () => {
  it("uses the PLAN online columns and never offers EH sorting", () => {
    expect(ONLINE_TABLE_COLUMNS.map((column) => column.key)).toEqual([
      "selection",
      "title",
      "category",
      "tags",
      "pages",
      "rating",
      "posted",
      "status",
    ]);
    expect(ONLINE_TABLE_COLUMNS.every((column) => column.sortKey === undefined)).toBe(true);
    expect(ONLINE_TABLE_COLUMNS.find((column) => column.key === "title")?.pinned).toBe(true);
  });
});

describe("posted normalisation", () => {
  it("converts UTC epoch seconds and rejects unknown values", () => {
    expect(normalizePosted(1761985800)).toBe("2025-11-01T08:30:00.000Z");
    expect(normalizePosted("1761985800")).toBe("2025-11-01T08:30:00.000Z");
    expect(normalizePosted(null)).toBeNull();
    expect(normalizePosted(0)).toBeNull();
    expect(normalizePosted(1970)).toBeNull();
    expect(normalizePosted("garbage")).toBeNull();
  });
});
