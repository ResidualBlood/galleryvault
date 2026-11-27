import { afterEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import TagGroups from "@/components/gallery/TagGroups.vue";
import { i18n, setLocale } from "@/i18n";
import type { GalleryTag } from "@/api/gallery";
import "@/components/tags/i18n";

const tags: GalleryTag[] = [
  { namespace: "artist", name: "zeta", display: "Zeta" },
  { namespace: "uploader", name: "uploader-one" },
  { namespace: "female", name: "heroine", display: "女主角" },
  { namespace: "parody", name: "series", display: "系列" },
  { namespace: "misc", name: "full color", display: "全彩" },
  { namespace: "artist", name: "alpha", display: "Alpha" },
  { namespace: "artist", name: "alpha", display: "Alpha" },
];

function mountTags(value: GalleryTag[] = tags) {
  return mount(TagGroups, {
    props: { tags: value },
    global: { plugins: [i18n] },
  });
}

describe("TagGroups", () => {
  afterEach(() => setLocale("zh"));

  it("groups tags by namespace in the canonical detail order", () => {
    const wrapper = mountTags();
    const groups = wrapper.findAll('[data-testid="tag-group"]');

    expect(groups.map((group) => group.attributes("data-ns"))).toEqual([
      "parody",
      "artist",
      "female",
      "misc",
      "uploader",
    ]);
  });

  it("sorts tags inside a namespace and de-duplicates namespace:name pairs", () => {
    const wrapper = mountTags();
    const artist = wrapper.get('[data-ns="artist"]');
    const chips = artist.findAll('[data-testid="tag-chip"]');

    expect(chips).toHaveLength(2);
    expect(chips.map((chip) => chip.text())).toEqual(["Alpha", "Zeta"]);
  });

  it("renders every chip at the 28px detail size", () => {
    const wrapper = mountTags();
    const chips = wrapper.findAll('[data-testid="tag-chip"]');
    expect(chips.length).toBeGreaterThan(0);
    for (const chip of chips) {
      expect(chip.attributes("data-size")).toBe("28");
    }
  });

  it("emits the selected tag", async () => {
    const wrapper = mountTags([{ namespace: "artist", name: "alpha" }]);
    await wrapper.get('[data-testid="tag-chip"]').trigger("click");

    expect(wrapper.emitted("select")?.[0]).toEqual([
      { namespace: "artist", name: "alpha" },
    ]);
  });

  it("renders the empty hint when there are no tags", () => {
    const wrapper = mountTags([]);

    expect(wrapper.find('[data-testid="tag-group"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="tag-empty"]').exists()).toBe(true);
  });

  it("has localized headings for cosplayer / reclass / temp in both locales", async () => {
    const extra: GalleryTag[] = [
      { namespace: "cosplayer", name: "cosplayer one" },
      { namespace: "reclass", name: "reclass one" },
      { namespace: "temp", name: "temp one" },
    ];
    const wrapper = mountTags(extra);

    const titles = () =>
      Object.fromEntries(
        wrapper
          .findAll('[data-testid="tag-group"]')
          .map((group) => [
            group.attributes("data-ns"),
            group.get(".tag-group__title").text(),
          ]),
      );

    setLocale("zh");
    await wrapper.vm.$nextTick();
    expect(titles()).toEqual({
      cosplayer: "Coser",
      reclass: "重分类",
      temp: "临时",
    });

    setLocale("en");
    await wrapper.vm.$nextTick();
    expect(titles()).toEqual({
      cosplayer: "Cosplayer",
      reclass: "Reclass",
      temp: "Temp",
    });
  });
});
