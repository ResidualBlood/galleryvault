import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useUiStore } from "../ui";

describe("ui store toasts", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("auto-dismisses a toast after the default TTL", () => {
    const ui = useUiStore();
    const id = ui.push("saved");

    expect(ui.toasts.map((toast) => toast.id)).toEqual([id]);
    vi.advanceTimersByTime(3999);
    expect(ui.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(ui.toasts).toHaveLength(0);
  });

  it("pauses on pointer and resumes with the remaining time", () => {
    const ui = useUiStore();
    const id = ui.push("saved");
    vi.advanceTimersByTime(1000);

    ui.pauseToast(id, "pointer");
    vi.advanceTimersByTime(60_000);
    expect(ui.toasts).toHaveLength(1);

    ui.resumeToast(id, "pointer");
    vi.advanceTimersByTime(2999);
    expect(ui.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(ui.toasts).toHaveLength(0);
  });

  it("stays paused while either pointer or focus remains", () => {
    const ui = useUiStore();
    const id = ui.push("saved");

    ui.pauseToast(id, "pointer");
    ui.pauseToast(id, "focus");
    ui.resumeToast(id, "pointer");
    vi.advanceTimersByTime(60_000);
    expect(ui.toasts).toHaveLength(1);

    ui.resumeToast(id, "focus");
    vi.advanceTimersByTime(3999);
    expect(ui.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(ui.toasts).toHaveLength(0);
  });

  it("clears the timer on manual dismiss and keeps the other toasts", () => {
    const ui = useUiStore();
    const first = ui.push("one");
    const second = ui.push("two");

    ui.dismiss(first);
    expect(ui.toasts.map((toast) => toast.id)).toEqual([second]);
    vi.advanceTimersByTime(4000);
    expect(ui.toasts).toHaveLength(0);
  });

  it("remembers the focused element and forgets it after dismissal", () => {
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();

    const ui = useUiStore();
    const id = ui.push("saved");
    expect(ui.returnFocusFor(id)).toBe(trigger);

    ui.dismiss(id);
    expect(ui.returnFocusFor(id)).toBeNull();
  });
});
