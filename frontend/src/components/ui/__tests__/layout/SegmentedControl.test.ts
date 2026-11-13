import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import SegmentedControl from "../../SegmentedControl.vue";
import { globalPlugins } from "./helpers";

const options = [
  { value: "grid", label: "Grid", icon: "view-grid" as const },
  { value: "list", label: "List", icon: "view-list" as const },
  { value: "table", label: "Table", icon: "view-table" as const, disabled: true },
];

function mountControl(modelValue = "grid") {
  return mount(SegmentedControl, {
    props: { modelValue, options, label: "View mode" },
    global: globalPlugins,
  });
}

describe("SegmentedControl", () => {
  it("renders a radiogroup with one checked radio and roving tabindex", () => {
    const wrapper = mountControl();
    const group = wrapper.find('[role="radiogroup"]');
    expect(group.attributes("aria-label")).toBe("View mode");
    const radios = wrapper.findAll('[role="radio"]');
    expect(radios).toHaveLength(3);
    expect(radios[0].attributes("aria-checked")).toBe("true");
    expect(radios[0].attributes("tabindex")).toBe("0");
    expect(radios[1].attributes("aria-checked")).toBe("false");
    expect(radios[1].attributes("tabindex")).toBe("-1");
    expect(radios[2].attributes("disabled")).toBeDefined();
  });

  it("emits the next value on arrow keys and wraps around", async () => {
    const wrapper = mountControl("grid");
    const first = wrapper.findAll('[role="radio"]')[0];
    await first.trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["list"]);

    const reversed = mountControl("list");
    const second = reversed.findAll('[role="radio"]')[1];
    await second.trigger("keydown", { key: "ArrowLeft" });
    expect(reversed.emitted("update:modelValue")?.[0]).toEqual(["grid"]);
  });

  it("skips disabled options and supports Home / End", async () => {
    const wrapper = mountControl("list");
    const second = wrapper.findAll('[role="radio"]')[1];
    await second.trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["grid"]);

    const all = mount(SegmentedControl, {
      props: {
        modelValue: "list",
        options: options.map((option) => ({ ...option, disabled: false })),
        label: "View mode",
      },
      global: globalPlugins,
    });
    const list = all.findAll('[role="radio"]')[1];
    await list.trigger("keydown", { key: "Home" });
    expect(all.emitted("update:modelValue")?.[0]).toEqual(["grid"]);
    await list.trigger("keydown", { key: "End" });
    expect(all.emitted("update:modelValue")?.[1]).toEqual(["table"]);
  });

  it("emits on click and does not re-emit the active value", async () => {
    const wrapper = mountControl("grid");
    const radios = wrapper.findAll('[role="radio"]');
    await radios[1].trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["list"]);
    await radios[0].trigger("click");
    expect(wrapper.emitted("update:modelValue")).toHaveLength(1);
  });

  it("maps the control ladder step onto the outer frame class", () => {
    const wrapper = mount(SegmentedControl, {
      props: { modelValue: "grid", options, label: "View mode", size: "sm" },
      global: globalPlugins,
    });
    expect(wrapper.classes()).toContain("segmented--sm");
  });
});
