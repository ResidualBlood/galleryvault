import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import Sheet from "../Sheet.vue";

function mountSheet(props: Record<string, unknown> = {}) {
  return mount(Sheet, {
    props: { open: false, ...props },
    slots: { default: "<p>body</p>" },
    attachTo: document.body,
  });
}

async function flush(): Promise<void> {
  await nextTick();
  await nextTick();
}

function rootEl(): HTMLDialogElement {
  const el = document.querySelector<HTMLDialogElement>("dialog.sheet");
  if (!el) throw new Error("sheet dialog not rendered");
  return el;
}

function panelEl(): HTMLElement {
  const el = document.querySelector<HTMLElement>(".sheet__panel");
  if (!el) throw new Error("sheet panel not rendered");
  return el;
}

function mockPanelRect(el: HTMLElement): void {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 500,
    right: 640,
    bottom: 900,
    width: 640,
    height: 400,
    x: 0,
    y: 500,
    toJSON: () => ({}),
  } as DOMRect);
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("Sheet", () => {
  it("opens modally and exposes the title through aria-labelledby", async () => {
    const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
    const wrapper = mountSheet({ open: true, title: "Tags" });
    await flush();

    const dialog = rootEl();
    expect(showModal).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(true);
    expect(dialog.getAttribute("role")).toBeNull();
    expect(dialog.getAttribute("aria-modal")).toBeNull();

    const title = dialog.querySelector<HTMLElement>(".sheet__title");
    expect(title?.textContent).toBe("Tags");
    expect(title?.id).toBeTruthy();
    expect(dialog.getAttribute("aria-labelledby")).toBe(title?.id);
    expect(panelEl().getAttribute("data-testid")).toBe("sheet");

    wrapper.unmount();
  });

  it("maps Esc/cancel to close without closing itself", async () => {
    const wrapper = mountSheet({ open: true, title: "Tags" });
    await flush();

    const event = new Event("cancel", { cancelable: true });
    rootEl().dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(wrapper.emitted("close")).toHaveLength(1);
    expect(rootEl().open).toBe(true);

    wrapper.unmount();
  });

  it("does not close when dismissible is false", async () => {
    const wrapper = mountSheet({ open: true, dismissible: false });
    await flush();
    mockPanelRect(panelEl());

    const event = new Event("cancel", { cancelable: true });
    rootEl().dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    rootEl().dispatchEvent(new MouseEvent("pointerdown", { clientX: 320, clientY: 10 }));
    rootEl().dispatchEvent(new MouseEvent("pointerup", { clientX: 320, clientY: 10 }));

    expect(wrapper.emitted("close")).toBeUndefined();
    expect(rootEl().open).toBe(true);

    wrapper.unmount();
  });

  it("dismisses on a press and release over the backdrop only", async () => {
    const wrapper = mountSheet({ open: true });
    await flush();
    mockPanelRect(panelEl());

    const dialog = rootEl();
    // Inside the panel: nothing happens.
    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 320, clientY: 700 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 320, clientY: 700 }));
    expect(wrapper.emitted("close")).toBeUndefined();

    // Backdrop press that releases inside the panel is not a dismiss.
    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 320, clientY: 100 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 320, clientY: 700 }));
    expect(wrapper.emitted("close")).toBeUndefined();

    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 320, clientY: 100 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 320, clientY: 100 }));
    expect(wrapper.emitted("close")).toHaveLength(1);

    wrapper.unmount();
  });

  it("ignores presses from a nested overlay outside the panel rect", async () => {
    const wrapper = mountSheet({ open: true });
    await flush();
    mockPanelRect(panelEl());

    const dialog = rootEl();
    const overlay = document.createElement("button");
    dialog.append(overlay);
    overlay.dispatchEvent(new MouseEvent("pointerdown", { clientX: 320, clientY: 10, bubbles: true }));
    overlay.dispatchEvent(new MouseEvent("pointerup", { clientX: 320, clientY: 10, bubbles: true }));
    expect(wrapper.emitted("close")).toBeUndefined();

    wrapper.unmount();
  });

  it("closes a still-open sheet when the owner unmounts it", async () => {
    const wrapper = mountSheet({ open: true });
    await flush();
    const dialog = rootEl();
    expect(dialog.open).toBe(true);

    wrapper.unmount();

    expect(dialog.open).toBe(false);
    expect(dialog.dataset.gvModal).toBeUndefined();
  });
});
