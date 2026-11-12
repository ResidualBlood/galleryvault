import { describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { routes } from "./routes";
import legacyRoutes from "../../parity/legacy-routes.json";
import waivers from "../../parity/waivers.json";

const waiverPaths = new Set(waivers.routes.map((item) => item.path));

function concretePath(path: string): string {
  return path.replace("{id}", "42").replace("{page}", "0");
}

function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

describe("legacy route parity", () => {
  const router = makeRouter();
  const legacy = legacyRoutes.routes.filter((route) => !waiverPaths.has(route.path));

  it.each(legacy.map((route) => [route.path, route.view] as const))(
    "resolves %s (legacy view %s)",
    (path) => {
      const resolved = router.resolve(concretePath(path));
      expect(resolved.matched.length).toBeGreaterThan(0);
      const last = resolved.matched.at(-1);
      expect(Boolean(resolved.name) || Boolean(last?.redirect)).toBe(true);
    },
  );

  it("keeps all documented aliases", () => {
    expect(router.resolve("/discover").name).toBe("online");
    expect(router.resolve("/duplicates/favorites").name).toBe("favorites-manage");
    expect(router.resolve("/favorites/manage").name).toBe("favorites-manage");
    expect(router.resolve("/favorites/ignored").name).toBe("favorites-ignored");
    expect(router.resolve("/duplicates/cross-gid").name).toBe("duplicates-cross-gid");
    expect(router.resolve("/updates/ignored").name).toBe("updates-ignored");
  });

  it("redirects the waived dead series detail route", () => {
    const resolved = router.resolve("/series/7");
    expect(resolved.matched.length).toBeGreaterThan(0);
    expect(String(resolved.matched.at(-1)?.redirect)).toBe("/series");
  });

  it("adds the new online routes with gid/token/page params", () => {
    const detail = router.resolve("/online/g/123/abc");
    expect(detail.name).toBe("online-detail");
    expect(detail.params).toMatchObject({ gid: "123", token: "abc" });
    const reader = router.resolve("/online/g/123/abc/read/4");
    expect(reader.name).toBe("online-reader");
    expect(reader.params).toMatchObject({ gid: "123", token: "abc", page: "4" });
  });

  it("does not expose /next/ or /legacy/ prefixes", () => {
    for (const route of routes) {
      const paths = [route.path, ...((route.alias as string[] | undefined) ?? [])];
      for (const path of paths) {
        expect(path.startsWith("/next/")).toBe(false);
        expect(path.startsWith("/legacy/")).toBe(false);
      }
    }
  });

  it("redirects unknown hash paths to browse", () => {
    expect(router.resolve("/no-such-page").name).toBeFalsy();
    expect(String(router.resolve("/no-such-page").matched[0]?.redirect)).toBe("/browse");
  });
});
