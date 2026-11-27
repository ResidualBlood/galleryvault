import { describe, expect, it } from "vitest";
import {
  formatEhTagQuery,
  libraryTagQuery,
  namespaceLabel,
  sortTagsForInline,
  tagKey,
  tagLabel,
  tagRawText,
  type TagLike,
} from "../tag-utils";

const female: TagLike = { namespace: "female", name: "big breasts", display: "巨乳" };

describe("tagLabel", () => {
  it("uses the display translation in Chinese", () => {
    expect(tagLabel(female, "zh")).toBe("巨乳");
    expect(tagLabel(female, "zh-CN")).toBe("巨乳");
  });

  it("falls back to the raw name when the display is missing", () => {
    expect(tagLabel({ namespace: "female", name: "big breasts" }, "zh")).toBe(
      "big breasts",
    );
    expect(tagLabel({ namespace: "female", name: "big breasts", display: "" }, "zh")).toBe(
      "big breasts",
    );
  });

  it("always uses the raw name outside Chinese", () => {
    expect(tagLabel(female, "en")).toBe("big breasts");
  });
});

describe("tagRawText / tagKey", () => {
  it("keeps the namespace prefix for copy and deduplication", () => {
    expect(tagRawText(female)).toBe("female:big breasts");
    expect(tagKey(female)).toBe("female:big breasts");
  });

  it("handles tags without a namespace", () => {
    expect(tagRawText({ namespace: null, name: "local tag" })).toBe("local tag");
    expect(tagKey({ name: "local tag" })).toBe("local tag");
  });
});

describe("namespaceLabel", () => {
  it("translates through gallery.namespaces and falls back to the raw namespace", () => {
    const t = (key: string) => (key === "gallery.namespaces.female" ? "女性" : key);
    expect(namespaceLabel("female", t)).toBe("女性");
    expect(namespaceLabel("unknown", t)).toBe("unknown");
    expect(namespaceLabel(null, t)).toBe("misc");
  });
});

describe("sortTagsForInline", () => {
  it("applies the product priority and drops language tags", () => {
    const tags: TagLike[] = [
      { namespace: "language", name: "chinese" },
      { namespace: "uploader", name: "someone" },
      { namespace: "other", name: "full color" },
      { namespace: "artist", name: "a" },
      { namespace: "character", name: "c" },
      { namespace: "female", name: "f" },
      { namespace: "cosplayer", name: "cos" },
      { namespace: "group", name: "g" },
      { namespace: "parody", name: "p" },
      { namespace: "male", name: "m" },
    ];

    expect(sortTagsForInline(tags).map((tag) => tag.namespace)).toEqual([
      "female",
      "male",
      "character",
      "parody",
      "artist",
      "group",
      "cosplayer",
      "other",
      "uploader",
    ]);
  });

  it("is stable for tags with the same rank", () => {
    const tags: TagLike[] = [
      { namespace: "artist", name: "first" },
      { namespace: "artist", name: "second" },
    ];
    expect(sortTagsForInline(tags).map((tag) => tag.name)).toEqual(["first", "second"]);
  });
});

describe("libraryTagQuery", () => {
  const tag: TagLike = { namespace: "female", name: "big breasts" };

  it("appends to the existing tags and pins tag_mode=and", () => {
    expect(libraryTagQuery("language:chinese", tag)).toEqual({
      tags: "language:chinese,female:big breasts",
      tag_mode: "and",
    });
  });

  it("is idempotent for a repeated positive tag", () => {
    const once = libraryTagQuery("language:chinese", tag);
    expect(libraryTagQuery(once.tags, tag)).toEqual(once);
    expect(libraryTagQuery("female:big breasts,female:big breasts", tag).tags).toBe(
      "female:big breasts",
    );
  });

  it("adds an exclusion and flips an existing positive token", () => {
    expect(libraryTagQuery("language:chinese", tag, { exclude: true })).toEqual({
      tags: "language:chinese,-female:big breasts",
      tag_mode: "and",
    });
    expect(libraryTagQuery("female:big breasts", tag, { exclude: true }).tags).toBe(
      "-female:big breasts",
    );
    expect(libraryTagQuery("-female:big breasts", tag).tags).toBe("female:big breasts");
  });

  it("accepts a route query object", () => {
    expect(libraryTagQuery({ tags: "language:chinese" }, tag).tags).toBe(
      "language:chinese,female:big breasts",
    );
  });
});

describe("formatEhTagQuery", () => {
  it("wraps names with spaces and ends with the exact marker", () => {
    expect(formatEhTagQuery("female", "big breasts")).toBe('female:"big breasts$"');
  });

  it("is idempotent for its own output and for pre-quoted input", () => {
    const once = formatEhTagQuery("female", "big breasts");
    expect(formatEhTagQuery("female", once)).toBe(once);
    expect(formatEhTagQuery("female", '"big breasts$"')).toBe(once);
    expect(formatEhTagQuery("female", 'female:"big breasts$"')).toBe(once);
  });

  it("keeps the compact form when the name has no whitespace", () => {
    expect(formatEhTagQuery("language", "chinese")).toBe("language:chinese$");
    expect(formatEhTagQuery("language", "language:chinese$")).toBe("language:chinese$");
  });

  it("applies the exact marker without a namespace", () => {
    expect(formatEhTagQuery(null, "big breasts")).toBe('"big breasts$"');
  });
});
