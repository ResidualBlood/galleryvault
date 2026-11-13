import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { h } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { i18n } from "@/i18n";
import PageHeader from "../../PageHeader.vue";
import { globalPlugins } from "./helpers";

describe("PageHeader", () => {
  it("renders an h1, count badge and the actions slot", () => {
    const wrapper = mount(PageHeader, {
      props: { title: "Library", count: 128, subtitle: "Local galleries" },
      slots: { actions: () => h("button", { class: "action" }, "Add") },
      global: globalPlugins,
    });
    const heading = wrapper.find("h1");
    expect(heading.text()).toBe("Library");
    expect(heading.classes()).toContain("page-header__title");
    expect(wrapper.find(".page-header__count").text()).toBe("128");
    expect(wrapper.find(".page-header__subtitle").text()).toBe("Local galleries");
    expect(wrapper.find(".action").exists()).toBe(true);
    expect(wrapper.find(".page-header__crumbs").exists()).toBe(false);
  });

  it("emits back from the optional back button", async () => {
    const wrapper = mount(PageHeader, {
      props: { title: "Gallery", back: true },
      global: globalPlugins,
    });
    await wrapper.find(".page-header__back").trigger("click");
    expect(wrapper.emitted("back")).toHaveLength(1);
  });

  it("renders breadcrumbs and marks the last one as current", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/browse", component: { template: "<div />" } }],
    });
    await router.push("/browse");
    await router.isReady();
    const wrapper = mount(PageHeader, {
      props: {
        title: "Library",
        crumbs: [{ label: "Home", to: "/browse" }, { label: "Library" }],
      },
      global: { plugins: [i18n, router] },
    });
    expect(wrapper.find(".page-header__crumbs").exists()).toBe(true);
    const crumbs = wrapper.findAll(".page-header__crumb");
    expect(crumbs[0].attributes("href")).toBe("/browse");
    expect(crumbs[1].attributes("aria-current")).toBe("page");
  });
});
