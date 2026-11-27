import { describe, expect, it } from "vitest";
import type { FavoriteItem } from "@/api/favorites";
import type { AppSettings } from "@/api/settings";
import { cloudOpenMode, externalUrl, planFavoriteOpen } from "../open";

function favorite(overrides: Partial<FavoriteItem> = {}): FavoriteItem {
  return {
    favcat: 3,
    gid: 5001,
    token: "abc123",
    title: "Sample gallery",
    title_jpn: null,
    url: "https://e-hentai.org/g/5001/abc123/",
    gallery_id: null,
    category: "manga",
    page_count: 24,
    cover_url: null,
    file_size: 1024,
    note: null,
    first_seen_at: "2025-10-01T10:00:00Z",
    is_local: false,
    tags: [],
    ...overrides,
  };
}

function settings(overrides: Partial<AppSettings> = {}): AppSettings {
  return {
    favorites_cloud_open: "app",
    exhentai_cookie_configured: true,
    ...overrides,
  };
}

describe("favorites cloud open mode", () => {
  it("defaults to app for a missing or unknown preference", () => {
    expect(cloudOpenMode(null)).toBe("app");
    expect(cloudOpenMode(settings({ favorites_cloud_open: undefined }))).toBe("app");
    expect(cloudOpenMode(settings({ favorites_cloud_open: "bogus" }))).toBe("app");
    expect(cloudOpenMode(settings({ favorites_cloud_open: "external" }))).toBe("external");
  });

  it("openFavorite routes cloud item to online-detail by default", () => {
    const plan = planFavoriteOpen(favorite(), settings());

    expect(plan.target).toEqual({ kind: "online", gid: 5001, token: "abc123" });
    expect(plan.cookieFallback).toBe(false);
  });

  it("openFavorite routes cloud item to online-detail before settings load", () => {
    const plan = planFavoriteOpen(favorite(), null);

    expect(plan.target).toEqual({ kind: "online", gid: 5001, token: "abc123" });
  });

  it("openFavorite opens external when setting is external", () => {
    const plan = planFavoriteOpen(favorite(), settings({ favorites_cloud_open: "external" }));

    expect(plan.target).toEqual({
      kind: "external",
      url: "https://e-hentai.org/g/5001/abc123/",
    });
    expect(plan.cookieFallback).toBe(false);
  });

  it("keeps local rows on the in-app gallery detail", () => {
    const plan = planFavoriteOpen(favorite({ gallery_id: 42, is_local: true }), settings());

    expect(plan.target).toEqual({ kind: "local", id: 42 });
  });

  it("falls back to the site when a cloud row has no token", () => {
    const plan = planFavoriteOpen(favorite({ token: "" }), settings());

    expect(plan.target.kind).toBe("external");
    expect(plan.cookieFallback).toBe(false);
  });

  it("falls back to the site with a hint when no EH cookies are configured", () => {
    const plan = planFavoriteOpen(favorite(), settings({ exhentai_cookie_configured: false }));

    expect(plan.target.kind).toBe("external");
    expect(plan.cookieFallback).toBe(true);
  });

  it("builds the E-Hentai URL from gid/token when the row has no url", () => {
    expect(externalUrl(favorite({ url: null, gid: 77, token: "t k" }))).toBe(
      "https://e-hentai.org/g/77/t%20k/",
    );
  });
});
