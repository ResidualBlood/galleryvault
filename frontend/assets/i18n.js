"use strict";

try {
  const th = localStorage.getItem("gv_theme");
  document.documentElement.setAttribute("data-theme", th === "light" ? "light" : "dark");
} catch (_) {}

// i18n.js — i18n dynamic loader & translation engine
// Locales are decoupled into assets/locales/{lang}.js and loaded on-demand.

window.GV_LOCALES = window.GV_LOCALES || {};
const I18N = window.GV_LOCALES;

async function loadLocale(lang) {
  if (I18N[lang]) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `/assets/locales/${encodeURIComponent(lang)}.js`;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      // Fallback: if requested lang fails and isn't 'en'/'zh', resolve anyway
      resolve();
    };
    document.head.appendChild(s);
  });
}

function t(key) {
  const cur = I18N[app.lang];
  if (cur && cur[key]) return cur[key];
  if (I18N.en && I18N.en[key]) return I18N.en[key];
  if (I18N.zh && I18N.zh[key]) return I18N.zh[key];
  return key;
}

function nsLabel(ns) {
  const cur = I18N[app.lang];
  if (cur && cur.ns && cur.ns[ns]) return cur.ns[ns];
  if (I18N.en && I18N.en.ns && I18N.en.ns[ns]) return I18N.en.ns[ns];
  if (I18N.zh && I18N.zh.ns && I18N.zh.ns[ns]) return I18N.zh.ns[ns];
  return ns;
}

function groupLabel(key) {
  const cur = I18N[app.lang];
  if (cur && cur.groups && cur.groups[key]) return cur.groups[key];
  if (I18N.en && I18N.en.groups && I18N.en.groups[key]) return I18N.en.groups[key];
  if (I18N.zh && I18N.zh.groups && I18N.zh.groups[key]) return I18N.zh.groups[key];
  return key;
}

function tagText(tag) {
  return app.lang === "zh" ? (tag.display || tag.name) : tag.name;
}
