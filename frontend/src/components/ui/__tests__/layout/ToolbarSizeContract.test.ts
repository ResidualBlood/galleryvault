import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { h } from "vue";
import Toolbar from "../../Toolbar.vue";
import Button from "../../Button.vue";
import Input from "../../Input.vue";
import { globalPlugins } from "./helpers";
import type { ControlSizeProp } from "../../control-size";

/**
 * Contract: a Toolbar is the single provider of the control size ladder.
 * Descendants without their own `size` must inherit the toolbar step, which is
 * the exact bug that used to happen when Toolbar published a string key while
 * every control injected `gvControlSize` (a Symbol).
 *
 * The step maps to tokens.css: `md` = 36px, `sm` = 32px (the legacy
 * `compact` alias resolves to `sm`).
 */

function mountToolbar(size: ControlSizeProp) {
  return mount(Toolbar, {
    props: { size },
    slots: {
      default: () => [
        h(Button, { variant: "outlined" }, () => "Sort"),
        h(Input, { modelValue: "nekopara", ariaLabel: "Search" }),
      ],
    },
    global: globalPlugins,
  });
}

describe("Toolbar control size contract", () => {
  it("passes the md (36px) step to Button and TextField descendants", () => {
    const wrapper = mountToolbar("md");

    expect(wrapper.attributes("data-size")).toBe("md");
    expect(wrapper.get("button").classes()).toContain("btn--md");
    expect(wrapper.get(".field").classes()).toContain("field--md");
  });

  it("resolves the legacy compact size to the sm (32px) step for descendants", () => {
    const wrapper = mountToolbar("compact");

    expect(wrapper.attributes("data-size")).toBe("sm");
    expect(wrapper.get("button").classes()).toContain("btn--sm");
    expect(wrapper.get(".field").classes()).toContain("field--sm");
  });

  it("defaults to the lg step for descendants that set no size", () => {
    const wrapper = mountToolbar("lg");

    expect(wrapper.attributes("data-size")).toBe("lg");
    expect(wrapper.get("button").classes()).toContain("btn--lg");
    expect(wrapper.get(".field").classes()).toContain("field--lg");
  });

  it("does not leak an explicit child size when the toolbar step changes", () => {
    const wrapper = mount(Toolbar, {
      props: { size: "compact" },
      slots: {
        default: () => [
          h(Button, { variant: "outlined", size: "lg" }, () => "Explicit"),
          h(Input, { modelValue: "x", ariaLabel: "Explicit" }),
        ],
      },
      global: globalPlugins,
    });

    expect(wrapper.get("button").classes()).toContain("btn--lg");
    expect(wrapper.get(".field").classes()).toContain("field--sm");
  });
});
