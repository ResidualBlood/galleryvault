"use strict";

// views/settings.js — Phase 1 continue
// renderSettings moved from app.js

async function renderSettings() {
  if (!app.settings) {
    try { app.settings = await api("GET", "/api/settings"); } catch (_) { app.settings = {}; }
  }
  const s = app.settings;
  const warnings = (s.library_root_warnings || [])
    .map(w => `<p class="notice">${esc(w)}</p>`).join("");
  $view().innerHTML = `
    <header><p class="eyebrow">CONFIGURATION</p><h1>${esc(t("settings"))}</h1>
    <p class="sub">${esc(t("settingsSub"))}</p></header>
    <form data-action="settings-save">
      <fieldset><legend>${esc(t("authLogin"))}</legend>
        <label class="checkbox"><input type="checkbox" name="auth_required"${s.auth_required == null ? " checked" : (s.auth_required ? " checked" : "")}> ${esc(t("authRequired"))}</label>
        <p class="notice">${s.auth_hash_configured ? esc(t("pwConfigured")) : esc(t("pwDefault"))}</p>
      </fieldset>
      <fieldset><legend>${esc(t("changePassword"))}</legend>
        ${field(t("currentPassword"), `<input name="current_password" type="password" autocomplete="current-password">`)}
        ${field(t("newPassword"), `<input name="new_password" type="password" autocomplete="new-password">`)}
        <button class="secondary" data-action="change-password" type="button">${esc(t("changePassword"))}</button>
      </fieldset>
      <fieldset><legend>ExHentai</legend>
        ${field(t("baseUrl"), ehBaseUrlControl(s.exhentai_base_url || "", ""))}
        ${/e-hentai\.org/i.test(s.exhentai_base_url || "") ? `<p class="notice">${esc(t("ehPublicNotice"))}</p>` : ""}
        <p class="notice">Cookie: <strong>${s.exhentai_cookie_configured ? esc(t("cookieSet")) : esc(t("cookieUnset"))}</strong> · ${esc(t("cookiesNote"))}</p>
        <div class="form-grid">
          <input name="ipb_member_id" placeholder="${esc(t("cookieId"))}" autocomplete="off">
          <input name="ipb_pass_hash" placeholder="${esc(t("cookieHash"))}" autocomplete="off">
          <input name="igneous" placeholder="${esc(t("cookieIgneous"))}" autocomplete="off">
        </div>
        <button class="secondary" data-action="test-exhentai" type="button">${esc(t("testExhentai"))}</button>
      </fieldset>
      <fieldset><legend>Proxy</legend>
        <div class="form-grid">
          ${field(t("proxyHttp"), `<input name="http_proxy" value="${esc(s.http_proxy || "")}">`)}
          ${field(t("proxySocks5"), `<input name="socks5_proxy" value="${esc(s.socks5_proxy || "")}">`)}
        </div>
      </fieldset>
      <fieldset><legend>${esc(t("libraryRoots"))}</legend>
        <p class="notice">${esc(t("libraryRootsHint"))}</p>
        <textarea name="library_roots" rows="4">${esc((s.library_roots || []).join("\n"))}</textarea>
        ${warnings}
      </fieldset>
      <fieldset><legend>Downloads</legend>
        <div class="form-grid">
          ${field(t("downloadRoot"), `<input name="download_root" value="${esc(s.download_root || "")}">`)}
          <p class="notice">${esc(t("downloadRootHint"))}</p>
          ${field(t("concurrency"), `<input name="download_concurrency" type="number" min="1" max="32" value="${s.download_concurrency != null ? s.download_concurrency : 2}">`)}
          ${field(t("pageConcurrency"), `<input name="page_concurrency" type="number" min="1" max="16" value="${s.page_concurrency != null ? s.page_concurrency : 4}">`)}
          ${field(t("quality"), `<select name="download_quality">
            <option value="original"${(s.download_quality || "resample") === "original" ? " selected" : ""}>${esc(t("qualityOriginal"))}</option>
            <option value="resample"${(s.download_quality || "resample") === "resample" ? " selected" : ""}>${esc(t("qualityResample"))}</option>
          </select>`)}
          ${field(t("downloadTitle"), `<select name="download_title">
            <option value="japanese"${(s.download_title || "japanese") === "japanese" ? " selected" : ""}>Japanese (日文)</option>
            <option value="english"${(s.download_title || "japanese") === "english" ? " selected" : ""}>English (英文)</option>
          </select>`)}
          ${field(t("titleDisplay"), `<select name="title_display">${["japanese", "english", "directory"].map(o => `<option value="${o}"${o === (s.title_display || "japanese") ? " selected" : ""}>${o}</option>`).join("")}</select>`)}
        </div>
        <p class="notice">${esc(t("imageTimeoutHint"))}</p>
        <div class="form-grid">
          ${field(t("imageTimeout"), `<input name="image_download_timeout_seconds" type="number" min="1" value="${s.image_download_timeout_seconds != null ? s.image_download_timeout_seconds : 120}">`)}
          ${field(t("imageWarmup"), `<input name="image_slow_warmup_seconds" type="number" min="1" value="${s.image_slow_warmup_seconds != null ? s.image_slow_warmup_seconds : 30}">`)}
          ${field(t("imageMinSpeed"), `<input name="image_min_speed_kb_s" type="number" min="1" value="${s.image_min_speed_kb_s != null ? s.image_min_speed_kb_s : 20}">`)}
        </div>
        <p class="notice">${esc(t("imageSlowHint"))}</p>
        <label class="checkbox"><input type="checkbox" name="use_hah"${s.use_hah ? " checked" : ""}> ${esc(t("useHah"))}</label>
        <label class="checkbox"><input type="checkbox" name="download_favorites_enabled"${s.download_favorites_enabled ? " checked" : ""}> download favorites</label>
        <div class="form-grid">
          ${field(t("archiveQuality"), `<select name="archive_quality">
            <option value="original"${(s.archive_quality || "resample") === "original" ? " selected" : ""}>${esc(t("archiveTierOriginal"))}</option>
            <option value="resample"${(s.archive_quality || "resample") === "resample" ? " selected" : ""}>${esc(t("archiveTierResample"))}</option>
          </select>`)}
        </div>
        <p class="notice">${esc(t("archiveMaxPagesHint"))}</p>
        <div class="form-grid">
          ${field(t("archiveMaxPages"), `<input name="favorites_archive_max_pages" type="number" min="0" value="${s.favorites_archive_max_pages != null ? s.favorites_archive_max_pages : 0}">`)}
        </div>
        <label class="checkbox"><input type="checkbox" name="favorites_archive_enabled"${s.favorites_archive_enabled ? " checked" : ""}> ${esc(t("archiveScanEnabled"))}</label>
        <label class="checkbox"><input type="checkbox" name="archive_fallback_pages"${s.archive_fallback_pages === false ? "" : " checked"}> ${esc(t("archiveFallbackPages"))}</label>
        <p class="notice">${esc(t("archiveFallbackPagesHint"))}</p>
      </fieldset>
      <fieldset><legend>Tags</legend>
        <label class="checkbox"><input type="checkbox" name="auto_sync_tags"${s.auto_sync_tags ? " checked" : ""}> ${esc(t("autoSyncTags"))}</label>
        <div class="form-grid">
          ${field(t("tagSyncInterval"), `<input name="tag_sync_interval_seconds" type="number" step="0.1" min="0.1" value="${s.tag_sync_interval_seconds != null ? s.tag_sync_interval_seconds : 1}">`)}
          ${field(t("tagSyncConcurrency"), `<input name="tag_sync_concurrency" type="number" min="1" max="32" value="${s.tag_sync_concurrency != null ? s.tag_sync_concurrency : 2}">`)}
        </div>
        <div class="toolbar"><button class="secondary" data-action="sync-all-tags" type="button">${esc(t("syncAllTags"))}</button>
          <a class="secondary" href="#/logs" style="padding:8px 14px;border-radius:4px">${esc(t("logs"))}</a></div>
      </fieldset>
      <fieldset><legend>Thumbnails</legend>
        <label class="checkbox"><input type="checkbox" name="generate_thumbnails"${s.generate_thumbnails ? " checked" : ""}> ${esc(t("generateThumbnails"))}</label>
        <div class="toolbar">
          <button class="secondary" data-action="gen-thumbs" type="button">${esc(t("genThumbs"))}</button>
          <a class="secondary" href="#/logs" style="padding:8px 14px;border-radius:4px">${esc(t("logs"))}</a>
        </div>
        <p class="notice" id="thumbs-status">${esc(t("thumbsHint"))}</p>
      </fieldset>
      <fieldset><legend>${esc(t("dupPolicy"))}</legend>
        <p class="notice">${esc(t("dupPolicyHint"))}</p>
        ${field(t("dupPolicy"), `<select name="duplicate_policy">
          ${[["keep_first", t("dupPolicyKeepFirst")], ["prefer_more_pages", t("dupPolicyMorePages")], ["prefer_newer", t("dupPolicyNewer")], ["prefer_larger", t("dupPolicyLarger")], ["prefer_smaller", t("dupPolicySmaller")], ["manual", t("dupPolicyManual")]].map(([o, label]) => `<option value="${o}"${o === (s.duplicate_policy || "keep_first") ? " selected" : ""}>${esc(label)}</option>`).join("")}
        </select>`)}
        <div class="toolbar"><a class="secondary" href="#/duplicates" style="padding:8px 14px;border-radius:4px">${esc(t("dupGalTitle"))}</a></div>
      </fieldset>
      <fieldset><legend>${esc(t("translationUpdate"))}</legend>
        ${field(t("translationInterval"), `<input name="tag_translation_update_interval_minutes" type="number" min="0" value="${s.tag_translation_update_interval_minutes != null ? s.tag_translation_update_interval_minutes : 720}">`)}
        <div class="toolbar"><button class="secondary" data-action="force-update" type="button">${esc(t("forceUpdate"))}</button></div>
        <p class="notice">${esc(t("translationStatus"))}: <span id="trans-status">${esc(s.translation ? s.translation : "")}</span></p>
      </fieldset>
      <fieldset><legend>Telegram</legend>
        ${field(t("botToken"), `<input name="telegram_bot_token" type="password" autocomplete="new-password" placeholder="${s.telegram_bot_configured ? t("cookieSet") : t("cookieUnset")}">`)}
        <div class="form-grid">
          ${field(t("chatIds"), `<input name="telegram_chat_ids" value="${esc((s.telegram_chat_ids || []).join(","))}">`)}
          ${field(t("allowedIds"), `<input name="telegram_allowed_user_ids" value="${esc((s.telegram_allowed_user_ids || []).join(","))}">`)}
          ${field(t("notifyLevel"), `<select name="telegram_notify_level">
            ${[["summary", t("notifyLevelSummary")], ["immediate", t("notifyLevelImmediate")], ["failures_only", t("notifyLevelFailuresOnly")], ["off", t("notifyLevelOff")]].map(([o, label]) => `<option value="${o}"${o === (s.telegram_notify_level || "summary") ? " selected" : ""}>${esc(label)}</option>`).join("")}
          </select>`)}
          ${field(t("notifyLang"), `<select name="telegram_notify_lang">
            ${[["zh", t("langZh")], ["en", t("langEn")]].map(([o, label]) => `<option value="${o}"${o === (s.telegram_notify_lang || app.lang) ? " selected" : ""}>${esc(label)}</option>`).join("")}
          </select>`)}
        </div>
        <button class="secondary" data-action="test-telegram" type="button">${esc(t("testTelegram"))}</button>
      </fieldset>
      <div class="toolbar"><button class="primary" type="submit">${esc(t("save"))}</button></div>
    </form>`;
  api("GET", "/api/tags/search/status").then(status => {
    const el = document.getElementById("trans-status");
    if (el && status) {
      const n = status.entries ? parseInt(status.entries, 10) : 0;
      const last = status.last ? new Date(status.last) : null;
      const when = last && !isNaN(last) ? last.toLocaleString() : (status.last || "");
      const err = status.last_error ? ` — ${esc(status.last_error)}` : "";
      el.textContent = (n > 0 ? `${n} entries, updated ${when}` : when) + err;
    }
  }).catch(() => {});
  refreshThumbsStatus();
}
