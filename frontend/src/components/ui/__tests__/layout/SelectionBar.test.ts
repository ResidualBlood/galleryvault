import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { h } from "vue";
import SelectionBar from "../../SelectionBar.vue";
import { globalPlugins } from "./helpers";

describe("SelectionBar", () => {
  it("renders nothing when no item is selected", () => {
    const wrapper = mount(SelectionBar, {
      props: { count: 0 },
      global: globalPlugins,
    });
    expect(wrapper.find('[data-testid="gv-selection-bar"]').exists()).toBe(false);
    expect(wrapper.text()).toBe("");
  });

  it("shows the selected count, actions and clear control", async () => {
    const wrapper = mount(SelectionBar, {
      props: { count: 3 },
      slots: {
        default: () => h("button", { class: "batch" }, "Archive"),
        danger: () => h("button", { class: "danger" }, "Delete"),
      },
      global: globalPlugins,
    });
    const bar = wrapper.find('[data-testid="gv-selection-bar"]');
    expect(bar.exists()).toBe(true);
    expect(bar.text()).toContain("已选 3 项");
    expect(bar.find(".batch").exists()).toBe(true);
    expect(bar.find(".danger").exists()).toBe(true);

    const text = bar.text();
    expect(text.indexOf("Archive")).toBeLessThan(text.indexOf("Delete"));
    expect(text.indexOf("Delete")).toBeLessThan(text.indexOf("清除选择"));

    await bar.find('[data-testid="gv-selection-clear"]').trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });
});
