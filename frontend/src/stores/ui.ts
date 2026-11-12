import { ref } from "vue";
import { defineStore } from "pinia";

export interface ToastMessage {
  id: number;
  text: string;
  kind: "info" | "success" | "error";
}

const TOAST_TTL_MS = 4000;

export const useUiStore = defineStore("ui", () => {
  const toasts = ref<ToastMessage[]>([]);
  let nextId = 1;

  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  function push(text: string, kind: ToastMessage["kind"] = "info"): number {
    const id = nextId++;
    toasts.value = [...toasts.value, { id, text, kind }];
    if (typeof window !== "undefined") {
      window.setTimeout(() => dismiss(id), TOAST_TTL_MS);
    }
    return id;
  }

  const info = (text: string) => push(text, "info");
  const success = (text: string) => push(text, "success");
  const error = (text: string) => push(text, "error");

  return { toasts, push, dismiss, info, success, error };
});
