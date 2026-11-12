import { useI18n } from "vue-i18n";
import { i18n } from "@/i18n";
import zhOnlineReader from "@/locales/zh/online-reader.json";
import enOnlineReader from "@/locales/en/online-reader.json";

/**
 * Online reader copy lives in its own namespace (`onlineReader.*`) so this
 * batch never has to touch the scaffold i18n entry point.
 */
let registered = false;

export function ensureOnlineReaderMessages(): void {
  if (registered) return;
  registered = true;
  i18n.global.mergeLocaleMessage("zh", { onlineReader: zhOnlineReader });
  i18n.global.mergeLocaleMessage("en", { onlineReader: enOnlineReader });
}

ensureOnlineReaderMessages();

export function useOnlineReaderI18n() {
  const { t } = useI18n();

  function tr(key: string, params?: Record<string, unknown>): string {
    const fullKey = `onlineReader.${key}`;
    const text = t(fullKey, params ?? {}, { missingWarn: false, fallbackWarn: false });
    return text === fullKey ? key : text;
  }

  return { tr };
}
