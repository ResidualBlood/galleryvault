import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { i18n, setLocale } from "@/i18n";
import TagMenu from "../TagMenu.vue";
import type { TagLike } from "../tag-utils";

const tag: TagLike = { namespace: "female", name: "big breasts", display: "巨乳" };

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/browse", name: "browse", component: { template: "<div />" } },
      { path: "/library", name: "library", component: { template: "<div />" } },
      { path: "/online", name: "online", component: { template: "<div />" } },
    ],
  });
}

async function mountMenu(source: "local" | "online" = "local") {
  const router = makeRouter();
  await router.push("/browse");
  await router.isReady();
  const wrapper = mount(TagMenu, {
    props: { tag, x: 120, y: 140, source },
    global: { plugins: [i18n, router], stubs: { teleport: true } },
  });
  return { wrapper, router };
}

describe("TagMenu", () => {
  beforeEach(() => {
    setLocale("zh");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("copies the raw ns:name text and closes", async () => {
    const { wrapper } = await mountMenu();
    await wrapper.get('[data-testid="tag-menu-copy"]').trigger("click");
    await flushPromises();

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("female:big breasts");
    expect(wrapper.emitted("copied")?.[0]).toEqual(["female:big breasts"]);
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  it("offers the four actions and shows the localised label plus raw text", async () => {
    const { wrapper } = await mountMenu();
    expect(wrapper.get('[data-testid="tag-menu"]').text()).toContain("巨乳");
    expect(wrapper.get('[data-testid="tag-menu"]').text()).toContain("female:big breasts");
    expect(wrapper.findAll('[role="menuitem"]')).toHaveLength(4);
  });

  it("filters the local library with tags and tag_mode=and", async () => {
    const { wrapper, router } = await mountMenu();
    await wrapper.get('[data-testid="tag-menu-filter"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("library");
    expect(router.currentRoute.value.query).toMatchObject({
      tags: "female:big breasts",
      tag_mode: "and",
    });
  });

  it("searches online with the exact ns:\"name$\" syntax", async () => {
    const { wrapper, router } = await mountMenu("online");
    await wrapper.get('[data-testid="tag-menu-search"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("online");
    expect(router.currentRoute.value.query.q).toBe('female:"big breasts$"');
  });

  it("excludes the tag locally", async () => {
    const { wrapper, router } = await mountMenu();
    await wrapper.get('[data-testid="tag-menu-exclude"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("library");
    expect(router.currentRoute.value.query.tags).toBe("-female:big breasts");
  });
});
