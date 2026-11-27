import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Icon from "../Icon.vue";
import { iconNames, iconRegistry, type IconName } from "../registry";

describe("icon registry", () => {
  it("registers every semantic name in a sorted list", () => {
    expect(iconNames.length).toBeGreaterThanOrEqual(50);
    expect([...iconNames].sort()).toEqual(iconNames);
    expect(new Set(iconNames)).toEqual(new Set(Object.keys(iconRegistry)));
  });

  it("renders every semantic name as an inline svg", () => {
    for (const name of iconNames) {
      const wrapper = mount(Icon, { props: { name } });
      expect(wrapper.element.tagName.toLowerCase(), name).toBe("svg");
      expect(wrapper.find("svg").exists(), name).toBe(true);
      expect(wrapper.classes(), name).toContain("gv-icon");
    }
  });

  it("rejects unknown names at the type layer", () => {
    // @ts-expect-error — IconName is a closed union of registry keys.
    const unknown: IconName = "not-a-real-icon";
    expect(unknown).toBe("not-a-real-icon");
  });

  it("maps each size prop to its dimension class", () => {
    for (const [size, expected] of [
      ["sm", "gv-icon--sm"],
      ["dense", "gv-icon--dense"],
      ["md", "gv-icon--md"],
      ["lg", "gv-icon--lg"],
    ] as const) {
      const wrapper = mount(Icon, { props: { name: "library", size } });
      expect(wrapper.classes(), size).toContain(expected);
    }
  });

  it("is decorative by default", () => {
    const wrapper = mount(Icon, { props: { name: "library" } });
    expect(wrapper.attributes("aria-hidden")).toBe("true");
    expect(wrapper.attributes("role")).toBeUndefined();
    expect(wrapper.attributes("aria-label")).toBeUndefined();
  });

  it("exposes an accessible name when labelled", () => {
    const wrapper = mount(Icon, { props: { name: "library", label: "本机库" } });
    expect(wrapper.attributes("role")).toBe("img");
    expect(wrapper.attributes("aria-label")).toBe("本机库");
    expect(wrapper.attributes("aria-hidden")).toBeUndefined();
  });
});
