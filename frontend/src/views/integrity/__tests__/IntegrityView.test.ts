import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import IntegrityView from "@/views/integrity/IntegrityView.vue";
import { fetchIntegrity } from "@/api/integrity";
import { redownloadGallery } from "@/api/gallery";
import { ApiError } from "@/api/client";
import { i18n } from "@/i18n";
import { useUiStore } from "@/stores/ui";

vi.mock("@/api/integrity", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/integrity")>();
  return {
    ...actual,
    fetchIntegrity: vi.fn(),
    scanIntegrity: vi.fn(),
  };
});

vi.mock("@/api/gallery", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/gallery")>();
  return { ...actual, redownloadGallery: vi.fn() };
});

const Stub = { template: "<div />" };

function pageFixture() {
  return {
    total: 1,
    page: 1,
    page_size: 50,
    magic_scan: {
      running: false,
      completed_at: "2026-11-01T12:00:00Z",
      scanned: 1,
      total: 1,
      corrupt: 1,
    },
    items: [
      {
        id: 3,
        gid: 300,
        title: "Missing pages",
        page_count: 10,
        actual_pages: 8,
      },
    ],
  };
}

function requiresCopy(): ApiError {
  return new ApiError("requires copy", {
    status: 409,
    detail: { code: "requires_copy" },
  });
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/maintenance/integrity", name: "integrity", component: Stub },
      { path: "/maintenance/recycle", name: "recycle", component: Stub },
      { path: "/maintenance/duplicates", name: "duplicates", component: Stub },
      { path: "/maintenance/favorites", name: "favorites-manage", component: Stub },
      { path: "/maintenance/cross-gid", name: "duplicates-cross-gid", component: Stub },
      { path: "/maintenance/archive", name: "archive", component: Stub },
      { path: "/gallery/:id", name: "gallery", component: Stub },
    ],
  });
  await router.push("/maintenance/integrity");
  await router.isReady();
  const pinia = createPinia();
  const wrapper = mount(IntegrityView, {
    attachTo: document.body,
    global: { plugins: [pinia, router, i18n] },
  });
  await flushPromises();
  return { wrapper, ui: useUiStore(pinia) };
}

async function selectAndRepair(wrapper: Awaited<ReturnType<typeof mountView>>["wrapper"]) {
  await wrapper.get('[data-testid="integrity-select-all"]').trigger("click");
  await wrapper.get('[data-testid="integrity-repair"]').trigger("click");
  await flushPromises();
}

describe("IntegrityView redownload confirmation", () => {
  beforeEach(() => {
    vi.mocked(fetchIntegrity).mockReset();
    vi.mocked(redownloadGallery).mockReset();
    vi.mocked(fetchIntegrity).mockResolvedValue(pageFixture());
    i18n.global.locale.value = "zh";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("asks before copying a library gallery and queues nothing on cancel", async () => {
    vi.mocked(redownloadGallery).mockRejectedValueOnce(requiresCopy());
    const { wrapper } = await mountView();

    await selectAndRepair(wrapper);

    expect(document.body.querySelector('[data-testid="integrity-copy-dialog"]')).not.toBeNull();
    const cancel = document.body.querySelector(
      '[data-testid="integrity-copy-cancel"]',
    ) as HTMLButtonElement;
    cancel.click();
    await flushPromises();

    expect(document.body.querySelector('[data-testid="integrity-copy-dialog"]')).toBeNull();
    expect(redownloadGallery).toHaveBeenCalledTimes(1);
    expect(vi.mocked(redownloadGallery).mock.calls[0]).toEqual([3]);
  });

  it("retries the pending ids with allow_copy after confirmation", async () => {
    vi.mocked(redownloadGallery)
      .mockRejectedValueOnce(requiresCopy())
      .mockResolvedValueOnce({ status: "pending" });
    const { wrapper, ui } = await mountView();

    await selectAndRepair(wrapper);

    const confirm = document.body.querySelector(
      '[data-testid="integrity-copy-confirm"]',
    ) as HTMLButtonElement;
    confirm.click();
    await flushPromises();

    expect(redownloadGallery).toHaveBeenLastCalledWith(3, { allowCopy: true });
    expect(ui.toasts.some((toast) => toast.kind === "success")).toBe(true);
  });
});
