import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import SettingsView from "@/views/settings/SettingsView.vue";
import { i18n } from "@/i18n";
import fixture from "../../../../e2e/fixtures/settings-sys/settings-get.json";

vi.mock("@/api/settings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/settings")>();
  return {
    ...actual,
    fetchSettings: vi.fn(async () => ({ ...fixture })),
    fetchThumbsStatus: vi.fn(async () => ({ running: false, succeeded: 3, failed: 0 })),
    fetchTagSearchStatus: vi.fn(async () => ({ entries: 45161 })),
  };
});

vi.mock("@/api/favorites", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/favorites")>();
  return {
    ...actual,
    fetchFavoriteCategories: vi.fn(async () => []),
  };
});

vi.mock("@/api/system", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/system")>();
  return {
    ...actual,
    fetchPause: vi.fn(async () => ({ paused: false })),
    setPaused: vi.fn(async (paused: boolean) => ({ paused })),
  };
});

const Stub = { template: "<div />" };

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", redirect: "/browse" },
      { path: "/browse", name: "browse", component: Stub },
      { path: "/login", name: "login", component: Stub },
      { path: "/settings/:group?", name: "settings", component: Stub },
    ],
  });
  await router.push(path);
  await router.isReady();

  const wrapper = mount(SettingsView, {
    global: { plugins: [createPinia(), router, i18n] },
  });
  await flushPromises();
  return { router, wrapper };
}

describe("settings group routing", () => {
  beforeEach(() => {
    i18n.global.locale.value = "zh";
  });

  it("keeps #/settings as the group index", async () => {
    const { router, wrapper } = await mountAt("/settings");
    expect(router.currentRoute.value.name).toBe("settings");
    expect(router.currentRoute.value.params.group ?? "").toBe("");
    expect(wrapper.get('[data-testid="settings-nav"]').classes()).not.toContain(
      "settings__nav--hidden",
    );
    expect(wrapper.get('[data-testid="settings-content"]').classes()).toContain(
      "settings__content--hidden",
    );
    wrapper.unmount();
  });

  it("opens the group named by the route parameter", async () => {
    const { router, wrapper } = await mountAt("/settings/download");
    expect(router.currentRoute.value.params.group).toBe("download");
    expect(wrapper.get('[data-testid="settings-content"]').classes()).not.toContain(
      "settings__content--hidden",
    );
    expect(wrapper.get('[data-testid="settings-nav"]').classes()).toContain(
      "settings__nav--hidden",
    );
    expect(wrapper.find('[data-settings-group="download"]').exists()).toBe(true);
    expect(wrapper.find('[data-settings-nav="download"]').attributes("aria-current")).toBe("page");
    wrapper.unmount();
  });

  it("syncs the route when a group is picked from the list", async () => {
    const { router, wrapper } = await mountAt("/settings");
    await wrapper.get('[data-settings-nav="tags"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.params.group).toBe("tags");
    expect(wrapper.find('[data-settings-group="tags"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("returns to the index through the back link", async () => {
    const { router, wrapper } = await mountAt("/settings/network");
    await wrapper.get('[data-testid="settings-back"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.params.group ?? "").toBe("");
    expect(wrapper.get('[data-testid="settings-nav"]').classes()).not.toContain(
      "settings__nav--hidden",
    );
    wrapper.unmount();
  });

  it("falls back to the index for an unknown group", async () => {
    const { router, wrapper } = await mountAt("/settings/does-not-exist");
    await flushPromises();
    expect(router.currentRoute.value.params.group ?? "").toBe("");
    expect(wrapper.get('[data-testid="settings-nav"]').classes()).not.toContain(
      "settings__nav--hidden",
    );
    wrapper.unmount();
  });
});
