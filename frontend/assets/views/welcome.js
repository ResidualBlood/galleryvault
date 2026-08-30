"use strict";

// views/welcome.js — Phase 1 extracted
// renderWelcome, renderLogin moved from app.js

async function renderWelcome() {
  let st = {};
  try { st = await api("GET", "/api/onboarding/status"); } catch (_) {}
  app.onboarding = st;
  const step = (done, body) => `
    <li class="wizard-step${done ? " done" : ""}">
      <div class="w-step">${done ? "✓" : "·"}</div>
      <div class="w-body">${body}</div>
    </li>`;
  const passwordBlock = st.password_default ? `
    <div class="w-form">
      <input name="current_password" type="password" placeholder="${esc(t("currentPassword"))}" autocomplete="current-password">
      <input name="new_password" type="password" placeholder="${esc(t("newPassword"))}" autocomplete="new-password">
      <button class="primary" data-action="welcome-change-password" type="button">${esc(t("changePassword"))}</button>
    </div>` : `<p class="w-ok">${esc(t("stepDone"))}</p>`;
  const cookieBlock = st.exhentai_configured ? `<p class="w-ok">${esc(t("stepDone"))}</p>` : `
    <div class="w-form">
      ${ehBaseUrlControl("https://exhentai.org", "w_")}
      <div class="w-grid">
        <input name="w_ipb_member_id" placeholder="${esc(t("cookieId"))}" autocomplete="off">
        <input name="w_ipb_pass_hash" placeholder="${esc(t("cookieHash"))}" autocomplete="off">
        <input name="w_igneous" placeholder="${esc(t("cookieIgneous"))}" autocomplete="off">
      </div>
      <div class="w-btns">
        <button class="secondary" data-action="welcome-save-cookie" type="button">${esc(t("save"))}</button>
        <button class="secondary" data-action="welcome-test-exhentai" type="button">${esc(t("testExhentai"))}</button>
      </div>
    </div>`;
  const importBlock = st.library_count > 0 ? `<p class="w-ok">${esc(t("stepDone"))} (${st.library_count})</p>` : `
    <p>${esc(t("welcomeImportHint"))}</p>
    <div class="w-btns">
      <button class="primary" data-action="welcome-check-favs" type="button">${esc(t("checkAll"))}</button>
      <button class="secondary" data-action="welcome-scan" type="button">${esc(t("scan"))}</button>
    </div>`;
  $view().innerHTML = `
    <div class="welcome">
      <header><p class="eyebrow">GETTING STARTED</p><h1>${esc(t("welcome"))}</h1>
      <p class="sub">${esc(t("welcomeSub"))}</p></header>
      <ol class="wizard">
        ${step(!st.password_default, `<h3>${esc(t("welcomePasswordTitle"))}</h3><p>${esc(t("welcomePasswordDesc"))}</p>${passwordBlock}`)}
        ${step(st.exhentai_configured, `<h3>${esc(t("welcomeCookieTitle"))}</h3><p>${esc(t("welcomeCookieDesc"))}</p>${cookieBlock}`)}
        ${step(st.library_count > 0, `<h3>${esc(t("welcomeImportTitle"))}</h3><p>${esc(t("welcomeImportDesc"))}</p>${importBlock}`)}
      </ol>
      <div class="wizard-actions">
        <button class="primary" data-action="welcome-finish" type="button">${esc(t("welcomeFinish"))}</button>
        ${st.password_default ? "" : `<button class="link-button" data-action="welcome-later" type="button">${esc(t("welcomeLater"))}</button>`}
      </div>
    </div>`;
}

function renderLogin() {
  $view().innerHTML = `
    <div class="login-wrap"><div class="panel">
      <p class="eyebrow">PRIVATE LIBRARY</p>
      <h1>GalleryVault</h1>
      <p class="sub">${esc(t("loginSub"))}</p>
      <form data-action="login">
        <label>${esc(t("password"))}<input name="password" type="password" autocomplete="current-password" autofocus></label>
        <button class="primary" type="submit">${esc(t("login"))}</button>
      </form>
    </div></div>`;
}
