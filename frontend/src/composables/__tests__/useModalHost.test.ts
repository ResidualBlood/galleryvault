import { afterEach, describe, expect, it } from "vitest";
import { findModalHost, MODAL_ATTR, useModalHost } from "../useModalHost";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("useModalHost", () => {
  it("falls back to body when no modal is open", () => {
    expect(findModalHost()).toBeNull();
    const { host } = useModalHost();
    expect(host.value).toBe("body");
  });

  it("picks the deepest open modal and can refresh or reset", () => {
    const outer = document.createElement("dialog");
    outer.setAttribute(MODAL_ATTR, "");
    const inner = document.createElement("dialog");
    inner.setAttribute(MODAL_ATTR, "");
    document.body.append(outer, inner);

    const { host, refresh, reset } = useModalHost();
    expect(host.value).toBe(inner);

    inner.removeAttribute(MODAL_ATTR);
    refresh();
    expect(host.value).toBe(outer);

    reset();
    expect(host.value).toBe("body");
  });

  it("ignores closed dialogs that no longer carry the modal marker", () => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.append(dialog);

    expect(findModalHost()).toBeNull();
    expect(useModalHost().host.value).toBe("body");
  });
});
