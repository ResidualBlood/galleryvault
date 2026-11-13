import { computed } from "vue";
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Button from "@/components/ui/Button.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Input from "@/components/ui/Input.vue";
import Select from "@/components/ui/Select.vue";
import {
  controlIconSize,
  gvControlSize,
  resolveControlSize,
  type ControlSize,
} from "@/components/ui/control-size";

/** Provide a container step exactly the way a Toolbar will. */
function provideSize(size: ControlSize) {
  return { [gvControlSize]: computed(() => size) };
}

describe("control size resolution", () => {
  it("maps legacy compact / small to sm and default to the inherited step", () => {
    expect(resolveControlSize("compact")).toBe("sm");
    expect(resolveControlSize("small")).toBe("sm");
    expect(resolveControlSize("default", "md")).toBe("md");
    expect(resolveControlSize(undefined, "md")).toBe("md");
    expect(resolveControlSize("default")).toBe("lg");
    expect(resolveControlSize(undefined)).toBe("lg");
  });

  it("lets an explicit prop override the inherited step", () => {
    expect(resolveControlSize("xl", "sm")).toBe("xl");
    expect(resolveControlSize("lg", "sm")).toBe("lg");
  });

  it("uses an 18px icon for the 32px step and 20px elsewhere", () => {
    expect(controlIconSize("sm")).toBe("dense");
    expect(controlIconSize("md")).toBe("md");
    expect(controlIconSize("lg")).toBe("md");
    expect(controlIconSize("xl")).toBe("md");
  });
});

describe("size inheritance through provide / inject", () => {
  it("inherits for every control when no size prop is passed", () => {
    const options = [{ value: "a", label: "A" }];

    const button = mount(Button, { global: { provide: provideSize("md") } });
    const iconButton = mount(IconButton, {
      props: { label: "Search" },
      global: { provide: provideSize("md") },
    });
    const input = mount(Input, { global: { provide: provideSize("md") } });
    const select = mount(Select, {
      props: { modelValue: "a", options },
      global: { provide: provideSize("md") },
    });

    expect(button.classes()).toContain("btn--md");
    expect(iconButton.classes()).toContain("icon-btn--md");
    expect(input.classes()).toContain("field--md");
    expect(select.classes()).toContain("select-field--md");
  });

  it("keeps an explicit size in front of the inherited one", () => {
    const button = mount(Button, {
      props: { size: "lg" },
      global: { provide: provideSize("sm") },
    });
    const input = mount(Input, {
      props: { size: "sm" },
      global: { provide: provideSize("lg") },
    });

    expect(button.classes()).toContain("btn--lg");
    expect(button.classes()).not.toContain("btn--sm");
    expect(input.classes()).toContain("field--sm");
  });

  it("defaults to lg at the top of the tree", () => {
    const button = mount(Button);
    const iconButton = mount(IconButton, { props: { label: "Search" } });
    expect(button.classes()).toContain("btn--lg");
    expect(iconButton.classes()).toContain("icon-btn--lg");
  });
});

describe("legacy size props", () => {
  it("maps Button compact and IconButton small to sm", () => {
    const button = mount(Button, { props: { size: "compact" } });
    const iconButton = mount(IconButton, { props: { label: "Search", size: "small" } });
    expect(button.classes()).toContain("btn--sm");
    expect(iconButton.classes()).toContain("icon-btn--sm");
  });

  it("keeps the old default size name working", () => {
    const button = mount(Button, { props: { size: "default" } });
    const iconButton = mount(IconButton, { props: { label: "Search", size: "default" } });
    expect(button.classes()).toContain("btn--lg");
    expect(iconButton.classes()).toContain("icon-btn--lg");
  });
});

/**
 * Compile-time contract: `label` is required. The assignment below is rejected
 * by vue-tsc, and `@ts-expect-error` keeps the check in the regular typecheck
 * run instead of a separate fixture.
 */
type IconButtonProps = InstanceType<typeof IconButton>["$props"];

describe("IconButton accessible name contract", () => {
  it("requires label at the type level", () => {
    const valid: IconButtonProps = { label: "Search" };
    // @ts-expect-error IconButton requires a label, so an empty props object is invalid.
    const missing: IconButtonProps = {};

    expect(valid.label).toBe("Search");
    expect(missing).toEqual({});
  });
});
