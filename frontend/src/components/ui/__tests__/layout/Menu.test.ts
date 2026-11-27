import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import Menu from "../../Menu.vue";
import { globalPlugins, stubMatchMedia } from "./helpers";

const items = [
  { id: "open", label: "Open", icon: "play" as const },
  { id: "copy", label: "Copy original", icon: "copy" as const },
  { id: "delete", label: "Delete", icon: "delete" as const, danger: true, separatorBefore: true },
];

function mountMenu() {
  return mount(Menu, {
    props: { items, label: "Gallery actions", testid: "menu" },
    global: globalPlugins,
    attachTo: document.body,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("Menu", () => {
  it("opens from the trigger and renders icon + text items", async () => {
    stubMatchMedia(true);
    const wrapper = mountMenu();
    await wrapper.find('[data-testid="menu-trigger"]').trigger("click");
    await nextTick();
    const entries = wrapper.findAll('[role="menuitem"]');
    expect(entries).toHaveLength(3);
    expect(entries[0].text()).toBe("Open");
    expect(entries[0].find("svg").exists()).toBe(true);
    expect(entries[2].classes()).toContain("menu__item--danger");
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1);
  });

  it("moves focus with arrow keys, Home / End and selects with click", async () => {
    stubMatchMedia(true);
    const wrapper = mountMenu();
    const trigger = wrapper.find('[data-testid="menu-trigger"]');
    await trigger.trigger("keydown", { key: "ArrowDown" });
    await nextTick();
    await nextTick();

    const entries = wrapper.findAll('[role="menuitem"]');
    expect(document.activeElement).toBe(entries[0].element);

    await entries[0].trigger("keydown", { key: "ArrowDown" });
    expect(document.activeElement).toBe(entries[1].element);

    await entries[1].trigger("keydown", { key: "End" });
    expect(document.activeElement).toBe(entries[2].element);

    await entries[2].trigger("keydown", { key: "Home" });
    expect(document.activeElement).toBe(entries[0].element);

    await entries[1].trigger("click");
    expect(wrapper.emitted("select")?.[0]).toEqual(["copy"]);
    await nextTick();
    expect(wrapper.find('[data-testid="menu-panel"]').exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
  });

  it("closes with Escape and returns focus to the trigger", async () => {
    stubMatchMedia(true);
    const wrapper = mountMenu();
    const trigger = wrapper.find('[data-testid="menu-trigger"]');
    await trigger.trigger("click");
    await nextTick();
    const entries = wrapper.findAll('[role="menuitem"]');
    await entries[0].trigger("keydown", { key: "Escape" });
    await nextTick();
    expect(wrapper.find('[data-testid="menu-panel"]').exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
  });
});
