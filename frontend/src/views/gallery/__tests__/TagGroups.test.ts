import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import TagGroups from "@/components/gallery/TagGroups.vue";
import { i18n } from "@/i18n";
import type { GalleryTag } from "@/api/gallery";
import "@/views/gallery/i18n";

const tags: GalleryTag[] = [
  { namespace: "artist", name: "zeta" },
  { namespace: "uploader", name: "uploader-one" },
  { namespace: "female", name: "heroine" },
  { namespace: "parody", name: "series" },
  { namespace: "misc", name: "full color" },
  { namespace: "artist", name: "alpha" },
  { namespace: "artist", name: "alpha" },
];

function mountTags(value: GalleryTag[] = tags) {
  return mount(TagGroups, {
    props: { tags: value },
    global: { plugins: [i18n] },
  });
}

describe("TagGroups", () => {
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
    expect(chips.map((chip) => chip.text())).toEqual(["alpha", "zeta"]);
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
});
