import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Tabs from "../../Tabs.vue";
import { globalPlugins } from "./helpers";

const items = [
  { value: "all", label: "All" },
  { value: "unread", label: "Unread" },
  { value: "downloaded", label: "Downloaded" },
];

describe("Tabs", () => {
  it("renders an underline tablist with roving tabindex", () => {
    const wrapper = mount(Tabs, {
      props: { items, modelValue: "unread", label: "Library tabs" },
      global: globalPlugins,
    });
    expect(wrapper.attributes("role")).toBe("tablist");
    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs).toHaveLength(3);
    expect(tabs[1].attributes("aria-selected")).toBe("true");
    expect(tabs[1].attributes("tabindex")).toBe("0");
    expect(tabs[0].attributes("tabindex")).toBe("-1");
  });

  it("emits on click and arrow keys", async () => {
    const wrapper = mount(Tabs, {
      props: { items, modelValue: "all", label: "Library tabs" },
      global: globalPlugins,
    });
    const tabs = wrapper.findAll('[role="tab"]');
    await tabs[2].trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["downloaded"]);

    await tabs[0].trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.emitted("update:modelValue")?.[1]).toEqual(["unread"]);
    await tabs[0].trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.emitted("update:modelValue")?.[2]).toEqual(["downloaded"]);
  });
});
