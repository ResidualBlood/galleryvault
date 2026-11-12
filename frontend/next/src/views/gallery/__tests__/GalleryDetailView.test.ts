import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import GalleryDetailView from "@/views/gallery/GalleryDetailView.vue";
import {
  getGallery,
  getGalleryProgress,
  type GalleryDetail,
} from "@/api/gallery";
import { i18n } from "@/i18n";
import { useUiStore } from "@/stores/ui";

vi.mock("@/api/gallery", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/gallery")>();
  return {
    ...actual,
    getGallery: vi.fn(),
    getGalleryProgress: vi.fn(),
  };
});

const Stub = { template: "<div />" };

function detailFixture(): GalleryDetail {
  return {
    id: 7,
    gid: 123456,
    token: "abcdef",
    title: "Test Gallery",
    title_jpn: "テストギャラリー",
    category: "doujinshi",
    page_count: 10,
    file_size: 1024 * 1024 * 12,
    uploader: "tester",
    posted_at: "2026-11-01T12:00:00Z",
    rating: 4.5,
    tags: [
      { namespace: "artist", name: "alpha" },
      { namespace: "parody", name: "series" },
    ],
    pages: Array.from({ length: 10 }, (_, index) => ({
      index,
      page_index: index,
      name: `${index + 1}.jpg`,
    })),
  };
}

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/browse", name: "browse", component: Stub },
      { path: "/gallery/:id", name: "gallery", component: Stub },
      { path: "/reader/:id/:page", name: "reader", component: Stub },
      { path: "/library", name: "library", component: Stub },
    ],
  });
  await router.push(path);
  await router.isReady();

  const pinia = createPinia();
  const wrapper = mount(GalleryDetailView, {
    global: { plugins: [pinia, router, i18n] },
  });
  await flushPromises();
  return { router, wrapper, ui: useUiStore(pinia) };
}

describe("GalleryDetailView", () => {
  beforeEach(() => {
    vi.mocked(getGallery).mockReset();
    vi.mocked(getGalleryProgress).mockReset();
  });

  it("returns home with a toast for a non-numeric gallery id", async () => {
    const { router, ui } = await mountAt("/gallery/abc");

    expect(getGallery).not.toHaveBeenCalled();
    expect(router.currentRoute.value.name).toBe("browse");
    expect(ui.toasts.some((toast) => toast.kind === "error")).toBe(true);
  });

  it("returns home for a missing gallery (404)", async () => {
    const { ApiError } = await import("@/api/client");
    vi.mocked(getGallery).mockRejectedValue(new ApiError("not found", { status: 404 }));
    vi.mocked(getGalleryProgress).mockRejectedValue(
      new ApiError("not found", { status: 404 }),
    );

    const { router, ui } = await mountAt("/gallery/7");

    expect(router.currentRoute.value.name).toBe("browse");
    expect(ui.toasts.some((toast) => toast.kind === "error")).toBe(true);
  });

  it("renders metadata, tags and the continue action from progress", async () => {
    vi.mocked(getGallery).mockResolvedValue(detailFixture());
    vi.mocked(getGalleryProgress).mockResolvedValue({
      gallery_id: 7,
      current_page: 3,
      total_pages: 10,
      updated_at: null,
    });

    const { router, wrapper } = await mountAt("/gallery/7");

    expect(wrapper.get('[data-testid="gallery-title"]').text()).toBe("Test Gallery");
    expect(wrapper.findAll('[data-testid="tag-group"]')).toHaveLength(2);
    expect(wrapper.findAll('[data-testid="thumb"]').length).toBeGreaterThan(0);

    const next = wrapper.get('[data-testid="continue-reading"]');
    expect(next.text()).toBe("继续阅读");
    await next.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/reader/7/3");
  });

  it("shows a retryable error state when the gallery request fails", async () => {
    vi.mocked(getGallery).mockRejectedValue(new Error("boom"));
    vi.mocked(getGalleryProgress).mockResolvedValue({
      gallery_id: 7,
      current_page: 0,
      total_pages: 10,
      updated_at: null,
    });

    const { wrapper } = await mountAt("/gallery/7");

    expect(wrapper.find('[data-testid="detail-error"]').exists()).toBe(true);
  });
});
