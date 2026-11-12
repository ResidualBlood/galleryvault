import { useI18n } from "vue-i18n";
import { i18n } from "@/i18n";
import zhReader from "@/locales/zh/reader.json";
import enReader from "@/locales/en/reader.json";

/**
 * Register the reader namespace on the shared i18n instance at import time.
 * `frontend/next/src/i18n/index.ts` is owned by the scaffold; merging here keeps
 * the reader copy in `locales/<lang>/reader.json` without editing that file.
 */
i18n.global.mergeLocaleMessage("zh", { reader: zhReader });
i18n.global.mergeLocaleMessage("en", { reader: enReader });

export function useReaderI18n() {
  const { t } = useI18n();

  function tr(key: string, params?: Record<string, unknown>): string {
    const fullKey = `reader.${key}`;
    const text = t(fullKey, params ?? {}, { missingWarn: false, fallbackWarn: false });
    return text === fullKey ? key : text;
  }

  return { tr };
}
