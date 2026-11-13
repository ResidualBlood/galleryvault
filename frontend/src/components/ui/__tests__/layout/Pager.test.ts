import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { h } from "vue";
import Pager from "../../Pager.vue";
import { globalPlugins } from "./helpers";

function mountPager(props: Record<string, unknown> = {}) {
  return mount(Pager, {
    props: { page: 2, totalPages: 10, ...props },
    global: globalPlugins,
  });
}

describe("Pager", () => {
  it("renders previous / page numbers / next and emits page changes", async () => {
    const wrapper = mountPager();
    expect(wrapper.find('[data-pager="prev"]').attributes("aria-label")).toBe("上一页");
    expect(wrapper.find('[data-pager="next"]').attributes("aria-label")).toBe("下一页");
    expect(wrapper.find('[aria-current="page"]').text()).toBe("2");

    await wrapper.find('[data-pager="next"]').trigger("click");
    expect(wrapper.emitted("update:page")?.[0]).toEqual([3]);

    await wrapper.find('[data-pager="prev"]').trigger("click");
    expect(wrapper.emitted("update:page")?.[1]).toEqual([1]);

    await wrapper.find('[aria-label="第 5 页"]').trigger("click");
    expect(wrapper.emitted("update:page")?.[2]).toEqual([5]);
  });

  it("disables previous on the first page", () => {
    const wrapper = mountPager({ page: 1 });
    expect(wrapper.find('[data-pager="prev"]').attributes("disabled")).toBeDefined();
  });

  it("rejects out-of-range jump values and keeps the current page", async () => {
    const wrapper = mountPager();
    const input = wrapper.find('[data-pager="jump"]');
    await input.setValue("0");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("update:page")).toBeUndefined();
    expect((input.element as HTMLInputElement).value).toBe("2");
    expect(input.attributes("aria-invalid")).toBe("true");

    await input.setValue("11");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("update:page")).toBeUndefined();
    expect((input.element as HTMLInputElement).value).toBe("2");
  });

  it("accepts an in-range jump value", async () => {
    const wrapper = mountPager();
    const input = wrapper.find('[data-pager="jump"]');
    await input.setValue("7");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("update:page")?.[0]).toEqual([7]);
  });

  it("submits the jump value on Enter and on blur without a hidden submit control", async () => {
    const wrapper = mountPager();
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false);

    const input = wrapper.find('[data-pager="jump"]');
    await input.setValue("4");
    await input.trigger("keydown.enter");
    expect(wrapper.emitted("update:page")?.[0]).toEqual([4]);

    await input.setValue("6");
    await input.trigger("blur");
    expect(wrapper.emitted("update:page")?.[1]).toEqual([6]);
  });

  it("rejects an out-of-range jump value on Enter", async () => {
    const wrapper = mountPager();
    const input = wrapper.find('[data-pager="jump"]');
    await input.setValue("99");
    await input.trigger("keydown.enter");
    expect(wrapper.emitted("update:page")).toBeUndefined();
    expect(input.attributes("aria-invalid")).toBe("true");
  });

  it("degrades to previous / next without a total and exposes the date slot", () => {
    const wrapper = mount(Pager, {
      props: { page: 1, totalPages: 0 },
      slots: { "date-jump": () => h("button", { class: "date-jump" }, "Date") },
      global: globalPlugins,
    });
    expect(wrapper.find('[data-pager="jump"]').exists()).toBe(false);
    expect(wrapper.findAll(".pager__page")).toHaveLength(0);
    expect(wrapper.find(".date-jump").exists()).toBe(true);
    expect(wrapper.find('[data-pager="prev"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-pager="next"]').attributes("disabled")).toBeUndefined();
  });

  it("emits the selected page size", async () => {
    const wrapper = mountPager({ pageSize: 24, pageSizeOptions: [24, 48, 96] });
    await wrapper.find("select").setValue("96");
    expect(wrapper.emitted("update:pageSize")?.[0]).toEqual([96]);
  });
});
