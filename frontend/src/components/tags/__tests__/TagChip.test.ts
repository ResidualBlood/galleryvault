import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { i18n, setLocale } from "@/i18n";
import TagChip from "../TagChip.vue";
import type { TagLike } from "../tag-utils";

const tag: TagLike = { namespace: "female", name: "big breasts", display: "巨乳" };

function mountChip(value: TagLike = tag) {
  return mount(TagChip, {
    props: { tag: value },
    global: { plugins: [i18n] },
  });
}

describe("TagChip", () => {
  beforeEach(() => setLocale("zh"));

  it("shows only the tag body, never the namespace prefix", () => {
    const wrapper = mountChip();
    expect(wrapper.text()).toContain("巨乳");
    expect(wrapper.text()).not.toContain("female");
    expect(wrapper.text()).not.toContain(":");
    expect(wrapper.find(".tag-chip__dot").exists()).toBe(true);
  });

  it("puts the namespace title and the raw tag in title / aria-label", () => {
    const wrapper = mountChip();
    expect(wrapper.attributes("title")).toBe("女性：female:big breasts");
    expect(wrapper.attributes("aria-label")).toBe("女性：female:big breasts");
  });

  it("follows the interface language without remounting", async () => {
    const wrapper = mountChip();
    expect(wrapper.text()).toContain("巨乳");
    setLocale("en");
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("big breasts");
    expect(wrapper.text()).not.toContain("巨乳");
  });

  it("emits select on click and stops the event from reaching a parent link", async () => {
    const wrapper = mountChip();
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("select")?.[0]).toEqual([tag]);
  });

  it("emits exclude for Shift / Ctrl clicks", async () => {
    const wrapper = mountChip();
    await wrapper.get("button").trigger("click", { shiftKey: true });
    await wrapper.get("button").trigger("click", { ctrlKey: true });
    expect(wrapper.emitted("exclude")).toHaveLength(2);
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("opens the menu from the context menu event", async () => {
    const wrapper = mountChip();
    await wrapper.get("button").trigger("contextmenu", {
      clientX: 40,
      clientY: 60,
    });
    expect(wrapper.emitted("menu")?.[0]?.[0]).toMatchObject({
      tag,
      x: 40,
      y: 60,
    });
  });

  it("uses the requested height token for each size", () => {
    const small = mountChip();
    const large = mount(TagChip, {
      props: { tag, size: 28 },
      global: { plugins: [i18n] },
    });
    expect(small.classes()).toContain("tag-chip--24");
    expect(large.classes()).toContain("tag-chip--28");
  });
});
