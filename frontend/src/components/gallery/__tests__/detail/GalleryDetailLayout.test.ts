import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import GalleryDetailLayout from "@/components/gallery/GalleryDetailLayout.vue";
import { i18n } from "@/i18n";

const Stub = { template: "<div />" };

function mountLayout(coverUrl = "/covers/7.jpg") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: Stub }],
  });
  return mount(GalleryDetailLayout, {
    props: { title: "Test Gallery", coverUrl, coverAlt: "cover" },
    global: { plugins: [router, i18n] },
  });
}

describe("GalleryDetailLayout cover priority", () => {
  it("marks the detail cover as the LCP candidate without lazy loading", () => {
    const image = mountLayout().get('[data-testid="detail-cover"]');

    expect(image.attributes("fetchpriority")).toBe("high");
    expect(image.attributes("loading")).toBeUndefined();
    expect(image.attributes("decoding")).toBe("async");
  });
});
