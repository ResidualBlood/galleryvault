import { i18n } from "@/i18n";
import zhUi from "@/locales/zh/ui.json";
import enUi from "@/locales/en/ui.json";

let registered = false;

/**
 * The shared controls own their messages (same pattern as
 * `components/actions/messages.ts`). Only the kit section and controls that
 * need text (clear button, slider value) call this; pure controls stay
 * i18n-free so they can render before the locale is resolved.
 */
export function ensureControlMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { ui: zhUi });
  i18n.global.mergeLocaleMessage("en", { ui: enUi });
}
