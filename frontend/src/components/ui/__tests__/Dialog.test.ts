import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import Dialog from "../Dialog.vue";

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(Dialog, {
    props: { open: false, ...props },
    slots: { default: "<p>body</p>" },
    attachTo: document.body,
  });
}

async function flush(): Promise<void> {
  await nextTick();
  await nextTick();
}

function dialogEl(): HTMLDialogElement {
  const el = document.querySelector<HTMLDialogElement>("dialog.dialog");
  if (!el) throw new Error("dialog not rendered");
  return el;
}

function panelEl(): HTMLElement {
  const el = document.querySelector<HTMLElement>(".dialog__panel");
  if (!el) throw new Error("dialog panel not rendered");
  return el;
}

function rect(left: number, top: number, right: number, bottom: number): DOMRect {
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

/** The root `<dialog>` spans the viewport; only `.dialog__panel` is the panel. */
function mockFullViewportRoot(): void {
  vi.spyOn(dialogEl(), "getBoundingClientRect").mockReturnValue(rect(0, 0, 1280, 900));
}

function mockPanel(): void {
  vi.spyOn(panelEl(), "getBoundingClientRect").mockReturnValue(rect(100, 100, 400, 400));
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("Dialog", () => {
  it("calls showModal when opened and labels itself from the visible title", async () => {
    const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
    const wrapper = mountDialog({ open: true, title: "Delete gallery" });
    await flush();

    const dialog = dialogEl();
    expect(showModal).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(true);
    expect(dialog.getAttribute("role")).toBeNull();
    expect(dialog.getAttribute("aria-modal")).toBeNull();

    const title = dialog.querySelector<HTMLElement>(".dialog__title");
    expect(title?.textContent).toBe("Delete gallery");
    expect(title?.id).toBeTruthy();
    expect(dialog.getAttribute("aria-labelledby")).toBe(title?.id);

    wrapper.unmount();
  });

  it("calls showModal only once the open prop flips to true", async () => {
    const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
    const wrapper = mountDialog();
    await flush();
    expect(showModal).not.toHaveBeenCalled();

    await wrapper.setProps({ open: true });
    await flush();
    expect(showModal).toHaveBeenCalledTimes(1);
    expect(dialogEl().open).toBe(true);

    wrapper.unmount();
  });

  it("turns a native cancel (Esc) into a close request and keeps ownership", async () => {
    const wrapper = mountDialog({ open: true, title: "Confirm" });
    await flush();

    const event = new Event("cancel", { cancelable: true });
    dialogEl().dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(wrapper.emitted("close")).toHaveLength(1);
    // The parent owns `open`; the dialog must not close itself.
    expect(dialogEl().open).toBe(true);

    wrapper.unmount();
  });

  it("ignores cancel and outside presses when not dismissible", async () => {
    const wrapper = mountDialog({ open: true, dismissible: false });
    await flush();

    const cancel = new Event("cancel", { cancelable: true });
    dialogEl().dispatchEvent(cancel);
    expect(cancel.defaultPrevented).toBe(true);

    const dialog = dialogEl();
    mockFullViewportRoot();
    mockPanel();
    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 10, clientY: 10 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 10, clientY: 10 }));

    expect(wrapper.emitted("close")).toBeUndefined();
    expect(dialog.open).toBe(true);

    wrapper.unmount();
  });

  it("closes on a press and release outside the panel, but not inside", async () => {
    const wrapper = mountDialog({ open: true });
    await flush();

    const dialog = dialogEl();
    // Regression: the full-viewport root must not make every click "inside".
    mockFullViewportRoot();
    mockPanel();

    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 200, clientY: 200 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 200, clientY: 200 }));
    expect(wrapper.emitted("close")).toBeUndefined();

    // A press inside that releases outside is a selection drag, not a dismiss.
    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 200, clientY: 200 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 10, clientY: 10 }));
    expect(wrapper.emitted("close")).toBeUndefined();

    dialog.dispatchEvent(new MouseEvent("pointerdown", { clientX: 10, clientY: 10 }));
    dialog.dispatchEvent(new MouseEvent("pointerup", { clientX: 10, clientY: 10 }));
    expect(wrapper.emitted("close")).toHaveLength(1);

    wrapper.unmount();
  });
});
