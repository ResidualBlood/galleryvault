import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import { i18n } from "@/i18n";
import FavPicker from "../FavPicker.vue";

function stubMedia(matches: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

async function mountPicker() {
  const wrapper = mount(FavPicker, {
    props: { open: true, gid: 42, token: "token-42", favorited: false, favcat: 0 },
    global: { plugins: [i18n, createPinia()] },
    attachTo: document.body,
  });
  await flushPromises();
  await nextTick();
  return wrapper;
}

function dialogEl(): HTMLDialogElement {
  const el = document.querySelector<HTMLDialogElement>("dialog.fav-picker");
  if (!el) throw new Error("fav picker dialog not rendered");
  return el;
}

describe("FavPicker", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    i18n.global.locale.value = "zh";
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline in unit test"))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("names the dialog from a visible h2 heading at the desktop breakpoint", async () => {
    stubMedia(false);
    const wrapper = await mountPicker();

    const dialog = dialogEl();
    expect(dialog.getAttribute("data-testid")).toBe("fav-picker");
    expect(dialog.getAttribute("aria-label")).toBeNull();

    const heading = dialog.querySelector<HTMLElement>("h2.fav-panel__title");
    expect(heading?.textContent?.trim()).toBe(i18n.global.t("actions.favoriteSelect"));
    expect(heading?.id).toBeTruthy();
    expect(dialog.getAttribute("aria-labelledby")).toBe(heading?.id);
    expect(dialog.querySelector(".fav-picker__handle")).toBeNull();

    wrapper.unmount();
  });

  it("keeps the same visible heading, dialog name and handle on the compact layout", async () => {
    stubMedia(true);
    const wrapper = await mountPicker();

    const dialog = dialogEl();
    expect(dialog.getAttribute("data-testid")).toBe("fav-sheet");

    const heading = dialog.querySelector<HTMLElement>("h2.fav-panel__title");
    expect(heading?.textContent?.trim()).toBe(i18n.global.t("actions.favoriteSelect"));
    expect(heading?.id).toBeTruthy();
    expect(dialog.getAttribute("aria-labelledby")).toBe(heading?.id);

    const handle = dialog.querySelector<HTMLElement>(".fav-picker__handle");
    expect(handle?.getAttribute("aria-hidden")).toBe("true");

    wrapper.unmount();
  });
});
