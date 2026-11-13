import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Checkbox from "@/components/ui/Checkbox.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";

describe("IconButton", () => {
  it("renders a registry icon and exposes label as aria-label and title", () => {
    const wrapper = mount(IconButton, { props: { label: "Search", name: "search" } });
    const button = wrapper.get("button");

    expect(button.attributes("aria-label")).toBe("Search");
    expect(button.attributes("title")).toBe("Search");
    expect(button.find("svg").exists()).toBe(true);
  });

  it("keeps supporting the legacy slot glyph while pages migrate", () => {
    const wrapper = mount(IconButton, {
      props: { label: "Menu" },
      slots: { default: "<span data-testid=\"legacy\">M</span>" },
    });
    expect(wrapper.find("[data-testid=\"legacy\"]").exists()).toBe(true);
  });
});

describe("Checkbox", () => {
  it("sets the native indeterminate property and aria-checked=mixed", async () => {
    const wrapper = mount(Checkbox, {
      props: { modelValue: false, indeterminate: true, label: "Partial" },
    });
    const input = wrapper.get("input");

    expect((input.element as HTMLInputElement).indeterminate).toBe(true);
    expect(input.attributes("aria-checked")).toBe("mixed");
  });

  it("clears indeterminate when the prop is removed", async () => {
    const wrapper = mount(Checkbox, {
      props: { modelValue: false, indeterminate: true },
    });
    await wrapper.setProps({ indeterminate: false });

    expect((wrapper.get("input").element as HTMLInputElement).indeterminate).toBe(false);
    expect(wrapper.get("input").attributes("aria-checked")).toBeUndefined();
  });

  it("emits the new checked value on change", async () => {
    const wrapper = mount(Checkbox, { props: { modelValue: false } });
    await wrapper.get("input").setValue(true);

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([true]);
    expect(wrapper.emitted("change")?.at(-1)).toEqual([true]);
  });
});

describe("TextField", () => {
  it("shows a clear button only while a value is present and clears through it", async () => {
    const wrapper = mount(Input, {
      props: { modelValue: "nekopara", clearable: true, clearLabel: "Clear" },
    });
    const clear = wrapper.get("button[aria-label=\"Clear\"]");

    await clear.trigger("click");

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([""]);
    expect(wrapper.emitted("change")?.at(-1)).toEqual([""]);
    expect(wrapper.emitted("clear")).toBeTruthy();
  });

  it("hides the clear button for empty or disabled fields", () => {
    const empty = mount(Input, { props: { modelValue: "", clearable: true } });
    const disabled = mount(Input, {
      props: { modelValue: "value", clearable: true, disabled: true },
    });

    expect(empty.find("button[aria-label=\"Clear\"]").exists()).toBe(false);
    expect(disabled.find("button[aria-label=\"Clear\"]").exists()).toBe(false);
  });

  it("marks the number variant so the native stepper is hidden and text is end-aligned", () => {
    const wrapper = mount(Input, { props: { type: "number", modelValue: "12" } });
    expect(wrapper.classes()).toContain("field--number");
    expect(wrapper.get("input").attributes("type")).toBe("number");
  });

  it("uses ariaLabel when there is no visual label", () => {
    const wrapper = mount(Input, { props: { ariaLabel: "Search galleries" } });
    expect(wrapper.get("input").attributes("aria-label")).toBe("Search galleries");
  });
});
