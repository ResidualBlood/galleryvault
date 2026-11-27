import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { defineComponent, h, inject, nextTick } from "vue";
import Toolbar from "../../Toolbar.vue";
import ToolbarGroup from "../../ToolbarGroup.vue";
import { gvControlSize } from "../../control-size";
import { globalPlugins, stubMatchMedia } from "./helpers";

const SizeProbe = defineComponent({
  setup() {
    const size = inject(gvControlSize);
    return () => h("span", { class: "size-probe" }, String(size?.value));
  },
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Toolbar", () => {
  it("exposes the data attribute and defaults to the lg control step", () => {
    const wrapper = mount(Toolbar, {
      slots: { default: () => h(SizeProbe) },
      global: globalPlugins,
    });
    expect(wrapper.attributes("data-gv-toolbar")).toBeDefined();
    expect(wrapper.attributes("data-size")).toBe("lg");
    expect(wrapper.find(".size-probe").text()).toBe("lg");
  });

  it("provides the requested control size to descendants", () => {
    const wrapper = mount(Toolbar, {
      props: { size: "md" },
      slots: { default: () => h(SizeProbe) },
      global: globalPlugins,
    });
    expect(wrapper.find(".size-probe").text()).toBe("md");
  });

  it("marks the end group and keeps groups as wrapping units", () => {
    const wrapper = mount(Toolbar, {
      slots: {
        default: () => [
          h(ToolbarGroup, { testid: "primary" }, () => h("button", "A")),
          h(ToolbarGroup, { end: true }, () => h("button", "B")),
        ],
      },
      global: globalPlugins,
    });
    const groups = wrapper.findAll("[data-gv-toolbar-group]");
    expect(groups).toHaveLength(2);
    expect(groups[1].attributes("data-end")).toBe("true");
  });

  it("moves a collapsible group into the compact overflow menu", async () => {
    stubMatchMedia(false);
    const wrapper = mount(Toolbar, {
      slots: {
        default: () => [
          h(ToolbarGroup, { testid: "primary" }, () => h("button", "A")),
          h(
            ToolbarGroup,
            { collapsible: true, testid: "collapsible" },
            () => h("button", "Import"),
          ),
        ],
      },
      global: globalPlugins,
    });
    await nextTick();
    await nextTick();
    expect(wrapper.find('[data-testid="collapsible"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="gv-toolbar-more-trigger"]').exists()).toBe(true);
  });

  it("keeps collapsible groups inline on wide viewports", async () => {
    stubMatchMedia(true);
    const wrapper = mount(Toolbar, {
      slots: {
        default: () =>
          h(
            ToolbarGroup,
            { collapsible: true, testid: "collapsible" },
            () => h("button", "Import"),
          ),
      },
      global: globalPlugins,
    });
    await nextTick();
    expect(wrapper.find('[data-testid="collapsible"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="gv-toolbar-more-trigger"]').exists()).toBe(false);
  });
});
