import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import GalleryManageSection from "@/views/gallery/extra/GalleryManageSection.vue";
import { ApiError } from "@/api/client";
import { redownloadGallery, type GalleryDetail } from "@/api/gallery";
import { i18n } from "@/i18n";
import { useUiStore } from "@/stores/ui";

vi.mock("@/api/gallery", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/gallery")>();
  return {
    ...actual,
    redownloadGallery: vi.fn(),
    getGalleryFavorite: vi.fn(async () => ({
      gid: 7,
      token: "tok",
      favorite: false,
      favcats: [],
      favcat_names: [],
      note: null,
    })),
    patchGalleryLocal: vi.fn(),
    setGalleryFavoriteNote: vi.fn(),
    deleteGallery: vi.fn(),
    downloadGalleryOriginal: vi.fn(),
  };
});

vi.mock("@/api/lists", () => ({
  fetchLists: vi.fn(async () => []),
  fetchGalleryLists: vi.fn(async () => []),
  addListItems: vi.fn(),
  removeListItems: vi.fn(),
}));

vi.mock("@/api/tags", () => ({ syncGalleryTags: vi.fn() }));

const Stub = { template: "<div />" };

function fixture(): GalleryDetail {
  return {
    id: 7,
    gid: 123,
    token: "tok",
    title: "Library copy",
    page_count: 10,
    storage_path: "/library/7-gallery",
  };
}

async function mountSection() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/gallery/:id", name: "gallery", component: Stub }],
  });
  await router.push("/gallery/7");
  await router.isReady();
  const pinia = createPinia();
  const wrapper = mount(GalleryManageSection, {
    props: { gallery: fixture() },
    attachTo: document.body,
    global: { plugins: [pinia, router, i18n] },
  });
  await flushPromises();
  return { wrapper, ui: useUiStore(pinia) };
}

function requiresCopy(): ApiError {
  return new ApiError("requires copy", {
    status: 409,
    detail: { code: "requires_copy" },
  });
}

describe("GalleryManageSection redownload confirmation", () => {
  beforeEach(() => {
    vi.mocked(redownloadGallery).mockReset();
    i18n.global.locale.value = "zh";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("opens the copy confirmation on 409 requires_copy and cancels without a task", async () => {
    vi.mocked(redownloadGallery).mockRejectedValueOnce(requiresCopy());
    const { wrapper } = await mountSection();

    await wrapper.get('[data-testid="redownload"]').trigger("click");
    await flushPromises();

    const dialog = document.body.querySelector('[data-testid="redownload-copy-dialog"]');
    expect(dialog).not.toBeNull();

    const cancel = document.body.querySelector(
      '[data-testid="redownload-copy-cancel"]',
    ) as HTMLButtonElement;
    cancel.click();
    await flushPromises();

    expect(document.body.querySelector('[data-testid="redownload-copy-dialog"]')).toBeNull();
    expect(redownloadGallery).toHaveBeenCalledTimes(1);
    expect(vi.mocked(redownloadGallery).mock.calls[0]).toEqual([7, { allowCopy: false }]);
  });

  it("retries with allow_copy after confirmation", async () => {
    vi.mocked(redownloadGallery)
      .mockRejectedValueOnce(requiresCopy())
      .mockResolvedValueOnce({ status: "pending" });
    const { wrapper, ui } = await mountSection();

    await wrapper.get('[data-testid="redownload"]').trigger("click");
    await flushPromises();

    const confirm = document.body.querySelector(
      '[data-testid="redownload-copy-confirm"]',
    ) as HTMLButtonElement;
    confirm.click();
    await flushPromises();

    expect(redownloadGallery).toHaveBeenLastCalledWith(7, { allowCopy: true });
    expect(ui.toasts.some((toast) => toast.kind === "success")).toBe(true);
  });
});
