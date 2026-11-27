import { afterEach, describe, expect, it } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import Popover from "../../Popover.vue";

const menuSlots = {
  trigger: '<button type="button" data-testid="trigger">Actions</button>',
  default: `<div data-testid="panel-body">
    <button type="button" role="menuitem" data-testid="item-1">One</button>
    <button type="button" role="menuitem" data-testid="item-2">Two</button>
    <button type="button" role="menuitem" data-testid="item-3">Three</button>
  </div>`,
};

const groupSlots = {
  trigger: '<button type="button" data-testid="trigger">Controls</button>',
  default: `<div data-testid="panel-body">
    <button type="button" data-testid="group-1">Pause</button>
    <button type="button" data-testid="group-2">Resume</button>
  </div>`,
};

function mountPopover(slots: Record<string, string>) {
  return mount(Popover, { attachTo: document.body, slots });
}

async function openPopover(wrapper: ReturnType<typeof mountPopover>) {
  await wrapper.get('[data-testid="trigger"]').trigger("click");
  await flushPromises();
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("Popover", () => {
  it("marks the slot trigger with aria-expanded and aria-haspopup", async () => {
    const wrapper = mountPopover(menuSlots);
    const trigger = wrapper.get('[data-testid="trigger"]');
    await flushPromises();
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(trigger.attributes("aria-haspopup")).toBe("menu");

    await openPopover(wrapper);
    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(trigger.attributes("aria-haspopup")).toBe("menu");
    expect(wrapper.get(".popover__panel").attributes("role")).toBe("menu");
  });

  it("moves focus to the first item on open and cycles with arrow / Home / End", async () => {
    const wrapper = mountPopover(menuSlots);
    await openPopover(wrapper);

    const [first, second, third] = [
      wrapper.get('[data-testid="item-1"]').element,
      wrapper.get('[data-testid="item-2"]').element,
      wrapper.get('[data-testid="item-3"]').element,
    ];
    expect(document.activeElement).toBe(first);

    first.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
    expect(document.activeElement).toBe(third);

    third.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.activeElement).toBe(first);

    first.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.activeElement).toBe(second);

    second.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
    expect(document.activeElement).toBe(third);

    third.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
    expect(document.activeElement).toBe(first);
  });

  it("closes with Escape and returns focus to the trigger", async () => {
    const wrapper = mountPopover(menuSlots);
    await openPopover(wrapper);
    const first = wrapper.get('[data-testid="item-1"]').element;
    expect(document.activeElement).toBe(first);

    first.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }),
    );
    await flushPromises();

    expect(wrapper.find(".popover__panel").exists()).toBe(false);
    expect(wrapper.get('[data-testid="trigger"]').attributes("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(wrapper.get('[data-testid="trigger"]').element);
  });

  it("closes on Tab", async () => {
    const wrapper = mountPopover(menuSlots);
    await openPopover(wrapper);
    wrapper
      .get('[data-testid="item-1"]')
      .element.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }),
      );
    await flushPromises();
    expect(wrapper.find(".popover__panel").exists()).toBe(false);
  });

  it("drops role=menu and focuses the first control for non-menuitem slots", async () => {
    const wrapper = mountPopover(groupSlots);
    await openPopover(wrapper);

    const panel = wrapper.get(".popover__panel");
    expect(panel.attributes("role")).toBeUndefined();
    expect(document.activeElement).toBe(wrapper.get('[data-testid="group-1"]').element);
    expect(wrapper.get('[data-testid="trigger"]').attributes("aria-haspopup")).toBeUndefined();
    expect(wrapper.get('[data-testid="trigger"]').attributes("aria-expanded")).toBe("true");
  });
});
