import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import CrossGidView from "@/views/duplicates/CrossGidView.vue";
import {
  dismissCrossGidDuplicate,
  fetchCrossGidDuplicates,
  restoreCrossGidDuplicate,
} from "@/api/duplicates";
import { i18n } from "@/i18n";

vi.mock("@/api/duplicates", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/duplicates")>();
  return {
    ...actual,
    fetchCrossGidDuplicates: vi.fn(),
    dismissCrossGidDuplicate: vi.fn(),
    restoreCrossGidDuplicate: vi.fn(),
    refreshCrossGidDuplicates: vi.fn(),
    removeFavorites: vi.fn(),
  };
});

const Stub = { template: "<div />" };

const OPEN_GROUP = {
  id: 71,
  key: "artist one|core title",
  artist: "artist one",
  status: "open",
  items: [
    { gid: 5001, gallery_id: 11, title: "Cross Local", display_title: "Cross Local" },
    { gid: 5002, title: "Cross Cloud", display_title: "Cross Cloud", url: "https://example.test/g/5002" },
  ],
};

const DISMISSED_GROUP = {
  id: 72,
  key: "artist two|ignored title",
  artist: "artist two",
  status: "dismissed",
  items: [{ gid: 5101, gallery_id: 12, title: "Ignored Cross", display_title: "Ignored Cross" }],
};

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/duplicates", name: "duplicates", component: Stub },
      { path: "/duplicates/favorites", name: "favorites-manage", component: Stub },
      { path: "/duplicates/cross-gid", name: "duplicates-cross-gid", component: Stub },
      { path: "/favorites/ignored", name: "favorites-ignored", component: Stub },
      { path: "/recycle", name: "recycle", component: Stub },
      { path: "/integrity", name: "integrity", component: Stub },
      { path: "/archive", name: "archive", component: Stub },
      { path: "/gallery/:id", name: "gallery", component: Stub },
    ],
  });
  await router.push("/duplicates/cross-gid");
  await router.isReady();
  const pinia = createPinia();
  const wrapper = mount(CrossGidView, {
    attachTo: document.body,
    global: { plugins: [pinia, router, i18n] },
  });
  await flushPromises();
  return { wrapper };
}

describe("CrossGidView persisted dismiss and restore", () => {
  beforeEach(() => {
    vi.mocked(fetchCrossGidDuplicates).mockReset();
    vi.mocked(dismissCrossGidDuplicate).mockReset();
    vi.mocked(restoreCrossGidDuplicate).mockReset();
    vi.mocked(fetchCrossGidDuplicates).mockResolvedValue({
      ready: true,
      count: 1,
      groups: [OPEN_GROUP],
    });
    vi.mocked(dismissCrossGidDuplicate).mockResolvedValue({ status: "dismissed" });
    vi.mocked(restoreCrossGidDuplicate).mockResolvedValue({ status: "open" });
    i18n.global.locale.value = "zh";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("dismisses a group through the cross-gid endpoint and hides it", async () => {
    const { wrapper } = await mountView();

    await wrapper.get('[data-testid="dupxgid-dismiss-71"]').trigger("click");
    await flushPromises();

    expect(dismissCrossGidDuplicate).toHaveBeenCalledWith(71);
    expect(wrapper.find('[data-testid="dupxgid-group-artist one|core title"]').exists()).toBe(
      false,
    );
  });

  it("ignored toggle lists dismissed groups and restores them", async () => {
    vi.mocked(fetchCrossGidDuplicates).mockImplementation(async (status) =>
      status === "dismissed"
        ? { ready: true, count: 1, groups: [DISMISSED_GROUP] }
        : { ready: true, count: 1, groups: [OPEN_GROUP] },
    );
    const { wrapper } = await mountView();

    await wrapper
      .get('[data-testid="dupxgid-status"] [data-segmented-value="dismissed"]')
      .trigger("click");
    await flushPromises();

    expect(fetchCrossGidDuplicates).toHaveBeenLastCalledWith("dismissed");
    expect(wrapper.find('[data-testid="dupxgid-group-artist two|ignored title"]').exists()).toBe(
      true,
    );

    await wrapper.get('[data-testid="dupxgid-restore-72"]').trigger("click");
    await flushPromises();

    expect(restoreCrossGidDuplicate).toHaveBeenCalledWith(72);
  });
});
