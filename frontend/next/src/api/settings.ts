import { ep } from "./client";

export const settingsEp = ep("GET", "/api/settings");
export const saveSettingsEp = ep("POST", "/api/settings");
export const cookieHealthEp = ep("GET", "/api/settings/cookie-health");
export const testExhentaiEp = ep("POST", "/api/settings/exhentai/test");
export const storageInfoEp = ep("GET", "/api/system/storage");
export const thumbsStatusEp = ep("GET", "/api/thumbs/status");
export const generateThumbsEp = ep("POST", "/api/thumbs/generate");
export const testTelegramEp = ep("POST", "/api/telegram/test");
