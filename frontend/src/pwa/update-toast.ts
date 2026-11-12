import enPwaRaw from "@/locales/en/pwa.json?raw";
import zhPwaRaw from "@/locales/zh/pwa.json?raw";
import { applyUpdate, PWA_UPDATE_EVENT } from "./register";
import "./update-toast.css";

interface Messages {
  updateAvailable: string;
  updateApply: string;
  dismiss: string;
}

// `?raw` keeps these as plain JSON: the Vue i18n plugin compiles every
// `src/locales/**` import into message functions, which this DOM-only module
// cannot render.
const EN = JSON.parse(enPwaRaw) as Messages;
const ZH = JSON.parse(zhPwaRaw) as Messages;

function messages(): Messages {
  const stored = localStorage.getItem("gv_lang");
  if (stored === "en") return EN;
  if (stored === "zh") return ZH;
  const lang = document.documentElement.lang || navigator.language || "en";
  return lang.toLowerCase().startsWith("zh") ? ZH : EN;
}

let toast: HTMLElement | null = null;

function remove(): void {
  toast?.remove();
  toast = null;
}

function show(): void {
  if (toast) return;
  const text = messages();

  const node = document.createElement("div");
  node.className = "gv-pwa-toast";
  node.dataset.testid = "pwa-update";
  node.setAttribute("role", "status");
  node.setAttribute("aria-live", "polite");

  const label = document.createElement("span");
  label.className = "gv-pwa-toast__text";
  label.textContent = text.updateAvailable;

  const action = document.createElement("button");
  action.type = "button";
  action.className = "gv-pwa-toast__action";
  action.dataset.testid = "pwa-update-apply";
  action.textContent = text.updateApply;
  action.addEventListener("click", () => {
    applyUpdate();
    remove();
  });

  const close = document.createElement("button");
  close.type = "button";
  close.className = "gv-pwa-toast__close";
  close.dataset.testid = "pwa-update-dismiss";
  close.setAttribute("aria-label", text.dismiss);
  close.textContent = "×";
  close.addEventListener("click", remove);

  node.append(label, action, close);
  document.body.append(node);
  toast = node;
}

/** Mount the update prompt and listen for the registration announcement. */
export function installUpdateToast(): void {
  window.addEventListener(PWA_UPDATE_EVENT, show);
}
