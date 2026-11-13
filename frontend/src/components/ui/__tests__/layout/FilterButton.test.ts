import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import FilterButton from "../../FilterButton.vue";
import { globalPlugins } from "./helpers";

describe("FilterButton", () => {
  it("hides the badge when no filter is active", () => {
    const wrapper = mount(FilterButton, {
      props: { count: 0 },
      global: globalPlugins,
    });
    expect(wrapper.find('[data-testid="gv-filter-badge"]').exists()).toBe(false);
    expect(wrapper.attributes("aria-label")).toBe("筛选");
  });

  it("shows a single-digit count and the 9+ cap", async () => {
    const wrapper = mount(FilterButton, {
      props: { count: 3 },
      global: globalPlugins,
    });
    const badge = wrapper.find('[data-testid="gv-filter-badge"]');
    expect(badge.text()).toBe("3");
    expect(wrapper.attributes("aria-label")).toContain("3 个筛选生效");

    await wrapper.setProps({ count: 12 });
    expect(wrapper.find('[data-testid="gv-filter-badge"]').text()).toBe("9+");
    expect(wrapper.attributes("aria-label")).toContain("12 个筛选生效");
  });

  it("uses the icon and label overrides", () => {
    const wrapper = mount(FilterButton, {
      props: { label: "Filter", count: 1 },
      global: globalPlugins,
    });
    expect(wrapper.text()).toContain("Filter");
    expect(wrapper.find("svg").exists()).toBe(true);
  });
});
