import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { i18n, setLocale } from "@/i18n";
import TagList from "../TagList.vue";
import type { TagLike } from "../tag-utils";

const tags: TagLike[] = [
  { namespace: "language", name: "chinese", display: "中文" },
  { namespace: "female", name: "big breasts", display: "巨乳" },
  { namespace: "male", name: "sole male", display: "单男" },
  { namespace: "character", name: "hatsune miku", display: "初音未来" },
  { namespace: "parody", name: "vocaloid", display: "VOCALOID" },
  { namespace: "artist", name: "sample artist", display: "示例作者" },
  { namespace: "group", name: "sample circle", display: "示例社团" },
  { namespace: "other", name: "full color", display: "全彩" },
];

function mountList(props: Record<string, unknown> = {}) {
  return mount(TagList, {
    props: { tags, ...props },
    global: { plugins: [i18n] },
  });
}

describe("TagList", () => {
  beforeEach(() => setLocale("zh"));

  it("shows max inline tags after the priority order and folds the rest into +N", () => {
    const wrapper = mountList({ max: 4 });
    const chips = wrapper.findAll('[data-testid="tag-list"] .tag-chip');
    expect(chips).toHaveLength(4);
    expect(chips.map((chip) => chip.text())).toEqual([
      "巨乳",
      "单男",
      "初音未来",
      "VOCALOID",
    ]);
    expect(wrapper.get('[data-testid="tag-more"]').text()).toBe("+4");
  });

  it("uses tag_count for the total when the backend already truncated the array", () => {
    const wrapper = mountList({ max: 4, tags: tags.slice(1, 5), tagCount: 12 });
    expect(wrapper.findAll('[data-testid="tag-list"] .tag-chip')).toHaveLength(4);
    expect(wrapper.get('[data-testid="tag-more"]').text()).toBe("+8");
  });

  it("never counts a larger tag_count as fewer hidden tags than the array length", () => {
    const wrapper = mountList({ max: 4, tagCount: 2 });
    expect(wrapper.get('[data-testid="tag-more"]').text()).toBe("+4");
  });

  it("opens the full list from +N and closes it with Escape", async () => {
    const wrapper = mountList({ max: 4 });
    await wrapper.get('[data-testid="tag-more"]').trigger("click");
    const panel = wrapper.get('[data-testid="tag-list-panel"]');
    expect(panel.findAll(".tag-chip")).toHaveLength(tags.length);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="tag-list-panel"]').exists()).toBe(false);
  });

  it("emits the tag selected from an inline chip", async () => {
    const wrapper = mountList({ max: 2 });
    await wrapper.findAll('[data-testid="tag-list"] .tag-chip')[0].trigger("click");
    expect(wrapper.emitted("select")?.[0]?.[0]).toMatchObject({
      namespace: "female",
      name: "big breasts",
    });
  });
});
