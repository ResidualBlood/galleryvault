import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BadgeStrip from "../../BadgeStrip.vue";

describe("BadgeStrip", () => {
  it("renders every badge when under the limit", () => {
    const wrapper = mount(BadgeStrip, {
      props: { badges: [{ label: "A" }, { label: "B" }] },
    });
    expect(wrapper.findAll(".badge").map((badge) => badge.text())).toEqual(["A", "B"]);
  });

  it("collapses overflow into +N", () => {
    const wrapper = mount(BadgeStrip, {
      props: {
        badges: [
          { label: "A" },
          { label: "B" },
          { label: "C" },
          { label: "D" },
          { label: "E" },
        ],
        max: 3,
      },
    });
    expect(wrapper.findAll(".badge").map((badge) => badge.text())).toEqual([
      "A",
      "B",
      "+3",
    ]);
  });

  it("maps category tones to token variables", () => {
    const wrapper = mount(BadgeStrip, {
      props: {
        badges: [
          {
            label: "同人志",
            tone: "category",
            colorToken: "--gv-cat-doujinshi",
          },
        ],
      },
    });
    const badge = wrapper.find(".badge");
    expect(badge.attributes("style")).toContain("--gv-cat-doujinshi");
  });
});
