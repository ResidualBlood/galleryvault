import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import Toast from "../Toast.vue";
import { i18n } from "@/i18n";
import { useUiStore } from "@/stores/ui";

type PopoverPrototype = HTMLElement & {
  popover?: string;
  showPopover?: () => void;
  hidePopover?: () => void;
};

let wrapper: VueWrapper | undefined;

function mountToast() {
  const pinia = createPinia();
  setActivePinia(pinia);
  wrapper = mount(Toast, {
    global: { plugins: [pinia, i18n] },
    attachTo: document.body,
  });
  return useUiStore();
}

function stubPopoverSupport() {
  const proto = HTMLElement.prototype as PopoverPrototype;
  const show = vi.fn();
  const hide = vi.fn();
  Object.defineProperty(proto, "popover", {
    configurable: true,
    get(this: HTMLElement) {
      return this.getAttribute("popover");
    },
    set(this: HTMLElement, value: string) {
      this.setAttribute("popover", value);
    },
  });
  Object.defineProperty(proto, "showPopover", { configurable: true, value: show });
  Object.defineProperty(proto, "hidePopover", { configurable: true, value: hide });
  return { show, hide };
}

function clearPopoverStubs() {
  const proto = HTMLElement.prototype as PopoverPrototype;
  Reflect.deleteProperty(proto, "popover");
  Reflect.deleteProperty(proto, "showPopover");
  Reflect.deleteProperty(proto, "hidePopover");
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  document.body.innerHTML = "";
  vi.useRealTimers();
  clearPopoverStubs();
});

describe("Toast", () => {
  it("renders one named live region without per-toast status roles", async () => {
    const ui = mountToast();
    ui.push("Saved", "success");
    await nextTick();

    const host = document.querySelector<HTMLElement>(".toast-host");
    expect(host).not.toBeNull();
    expect(host?.getAttribute("role")).toBe("region");
    expect(host?.getAttribute("aria-label")).toBe("通知");
    expect(host?.getAttribute("aria-live")).toBe("polite");
    expect(host?.querySelectorAll('[role="status"]')).toHaveLength(0);
    expect(host?.querySelector(".toast")?.hasAttribute("role")).toBe(false);
  });

  it("falls back to fixed positioning when popover is unsupported", async () => {
    const ui = mountToast();
    ui.push("Saved");
    await nextTick();

    const host = document.querySelector<HTMLElement>(".toast-host");
    expect(host?.hasAttribute("popover")).toBe(false);
    expect(host?.querySelector(".toast")).not.toBeNull();
  });

  it("pauses auto-dismiss while hovering and resumes with the remaining time", async () => {
    const ui = mountToast();
    ui.push("Saved");
    await nextTick();

    const toast = document.querySelector<HTMLElement>(".toast");
    expect(toast).not.toBeNull();
    vi.advanceTimersByTime(1000);

    toast?.dispatchEvent(new Event("pointerenter"));
    vi.advanceTimersByTime(30_000);
    expect(ui.toasts).toHaveLength(1);

    toast?.dispatchEvent(new Event("pointerleave"));
    vi.advanceTimersByTime(2999);
    expect(ui.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(ui.toasts).toHaveLength(0);
  });

  it("pauses auto-dismiss while a control inside the toast has focus", async () => {
    const ui = mountToast();
    ui.push("Saved");
    await nextTick();

    const close = document.querySelector<HTMLElement>(".toast__close");
    close?.focus();
    vi.advanceTimersByTime(30_000);
    expect(ui.toasts).toHaveLength(1);

    close?.blur();
    vi.advanceTimersByTime(4000);
    expect(ui.toasts).toHaveLength(0);
  });

  it("moves focus to the next toast, then back to the trigger", async () => {
    const ui = mountToast();
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();

    ui.push("One");
    ui.push("Two");
    await nextTick();

    const firstClose = document.querySelector<HTMLElement>('[data-toast-id="1"] .toast__close');
    firstClose?.focus();
    firstClose?.click();
    await nextTick();
    await nextTick();

    expect(ui.toasts.map((toast) => toast.id)).toEqual([2]);
    expect(document.activeElement).toBe(
      document.querySelector('[data-toast-id="2"] .toast__close'),
    );

    (document.activeElement as HTMLElement | null)?.click();
    await nextTick();
    await nextTick();

    expect(ui.toasts).toHaveLength(0);
    expect(document.activeElement).toBe(trigger);
  });

  it("promotes the host to the top layer and re-shows it for new toasts", async () => {
    const { show, hide } = stubPopoverSupport();
    const ui = mountToast();
    await nextTick();

    const host = document.querySelector<HTMLElement>(".toast-host");
    expect(host?.getAttribute("popover")).toBe("manual");

    ui.push("One");
    await nextTick();
    expect(show).toHaveBeenCalledTimes(1);

    // Focus inside the toast must not be blurred by a re-show.
    const close = document.querySelector<HTMLElement>(".toast__close")!;
    const active = vi.spyOn(document, "activeElement", "get").mockReturnValue(close);
    ui.push("Two");
    await nextTick();
    expect(show).toHaveBeenCalledTimes(1);
    active.mockRestore();

    ui.push("Three");
    await nextTick();
    expect(hide).toHaveBeenCalled();
    expect(show).toHaveBeenCalledTimes(2);
  });
});
