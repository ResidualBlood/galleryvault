import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { i18n } from "@/i18n";
import FavButton from "@/components/actions/FavButton.vue";
import GalleryActions from "@/components/actions/GalleryActions.vue";
import { useUiStore } from "@/stores/ui";
import { createDownloadEp } from "@/api/downloads";
import { ehStatusEp } from "@/api/eh";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const ADD_OK = {
  gids: [42],
  target_favcat: 3,
  cloud_ok: true,
  cloud_added: 1,
  cloud_failed: [],
  successful_gids: [42],
  local_added: 1,
};

function mountFav() {
  return mount(FavButton, {
    props: { gid: 42, token: "token-42" },
    global: { plugins: [i18n] },
  });
}

describe("quick action components", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    document.cookie = "galleryvault_csrf=test-csrf";
    i18n.global.locale.value = "zh";
    vi.unstubAllGlobals();
  });

  it("one click adds to gv_default_favcat and paints the slot colour", async () => {
    localStorage.setItem("gv_default_favcat", "3");
    const fetchMock = vi.fn(async () => jsonResponse(ADD_OK));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mountFav();

    await wrapper.get('[data-testid="fav-button"]').trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(wrapper.get('[data-testid="fav-heart"]').attributes("data-favcat")).toBe("3");
    expect(wrapper.get('[data-testid="fav-button"]').attributes("aria-pressed")).toBe("true");
  });

  it("keeps the heart unselected and shows an error toast when the API returns 500", async () => {
    localStorage.setItem("gv_default_favcat", "3");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "boom" }, 500)));
    const wrapper = mountFav();

    await wrapper.get('[data-testid="fav-button"]').trigger("click");
    await flushPromises();

    expect(wrapper.get('[data-testid="fav-heart"]').attributes("data-favcat")).toBeUndefined();
    expect(wrapper.get('[data-testid="fav-button"]').attributes("aria-pressed")).toBe("false");
    const toasts = useUiStore().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({ kind: "error" });
  });

  it("sends only one add request for two rapid clicks", async () => {
    localStorage.setItem("gv_default_favcat", "3");
    let resolve!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mountFav();

    const button = wrapper.get('[data-testid="fav-button"]');
    await button.trigger("click");
    await button.trigger("click");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolve(jsonResponse(ADD_OK));
    await flushPromises();
    expect(wrapper.get('[data-testid="fav-heart"]').attributes("data-favcat")).toBe("3");
  });

  it("queues a download and drives the badge, sending CSRF and quality", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === ehStatusEp.path) {
        return jsonResponse({ items: [] });
      }
      if (url.pathname === createDownloadEp.path && init?.method === "POST") {
        return jsonResponse({ id: 9, gid: 7, title: "T", status: "pending" }, 202);
      }
      return jsonResponse({ total: 0, page: 1, page_size: 500, items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(GalleryActions, {
      props: { gid: 7, token: "token-7", title: "T", density: "detail" },
      global: { plugins: [i18n] },
    });

    await wrapper.get('[data-testid="download-button"]').trigger("click");
    await flushPromises();

    const badge = wrapper.get('[data-testid="download-badge"]');
    expect(badge.attributes("data-status")).toBe("queued");
    expect(badge.text()).toBe("排队");

    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        new URL(String(url), "http://localhost").pathname === createDownloadEp.path &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(post).toBeTruthy();
    const init = post?.[1] as RequestInit;
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("test-csrf");
    expect(JSON.parse(String(init.body))).toEqual({
      gid: 7,
      token: "token-7",
      title: "T",
      quality: "resample",
    });
  });
});
