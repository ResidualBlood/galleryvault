"use strict";

try {
  const th = localStorage.getItem("gv_theme");
  document.documentElement.setAttribute("data-theme", th === "light" ? "light" : "dark");
} catch (_) {}

// i18n.js — i18n dynamic loader & translation engine
// Locales are decoupled into assets/locales/{lang}.js and loaded on-demand.

window.GV_LOCALES = window.GV_LOCALES || {};
const I18N = window.GV_LOCALES;

const I18N_BUILTIN = {
  zh: {
    repair_categories_btn: "本地分类秒级自愈",
    repair_categories_hint: "基于本地元数据与 .galleryvault.json 秒级同步并修正画廊分类，无需访问外网，立即自愈误归入 Misc/Other 的作品。",
    repair_categories_running: "正在自愈分类...",
    repair_categories_done: "分类自愈完成：已修复 {repaired} 本画廊（扫描总量 {total}）",
    purge_archived_sources_btn: "清理已归档源目录残留文件",
    purge_archived_sources_tip: "安全机制：后台自动校验冷热端 GID 一致性，严密排除待下载、正在下载及活跃任务，仅清理已在冷存储生成完好 CBZ 归档的解压源文件夹，零风险释放热存储下载空间。",
    purge_safemode_active: "安全防护启用",
    repairCategories: "本地分类秒级自愈",
    repairCategoriesHint: "基于本地元数据与 .galleryvault.json 秒级同步并修正画廊分类，无需访问外网，立即自愈误归入 Misc/Other 的作品。",
    purgeArchivedSourcesBtn: "清理已归档源目录残留文件",
  },
  en: {
    repair_categories_btn: "Repair Categories (Local)",
    repair_categories_hint: "Synchronizes gallery categories from local metadata and .galleryvault.json in seconds without external network calls, instantly fixing misclassified Misc/Other items.",
    repair_categories_running: "Repairing categories...",
    repair_categories_done: "Categories repaired: {repaired} updated out of {total} total.",
    purge_archived_sources_btn: "Purge Archived Sources",
    purge_archived_sources_tip: "Safety Guarantee: Reconciles cold and hot storage GIDs, strictly excludes pending and active downloads, safely deleting unpacked source folders only when confirmed CBZ archives exist in cold storage.",
    purge_safemode_active: "Safe Mode Active",
    repairCategories: "Repair Categories (Local)",
    repairCategoriesHint: "Synchronizes gallery categories from local metadata and .galleryvault.json in seconds without external network calls, instantly fixing misclassified Misc/Other items.",
    purgeArchivedSourcesBtn: "Purge Archived Sources",
  },
};

window.GV_LOCALES.zh = Object.assign({}, I18N_BUILTIN.zh, window.GV_LOCALES.zh);
window.GV_LOCALES.en = Object.assign({}, I18N_BUILTIN.en, window.GV_LOCALES.en);

async function loadLocale(lang) {
  if (I18N[lang]) {
    if (I18N_BUILTIN[lang]) Object.assign(I18N[lang], I18N_BUILTIN[lang]);
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `/assets/locales/${encodeURIComponent(lang)}.js`;
    s.async = true;
    s.onload = () => {
      if (I18N[lang] && I18N_BUILTIN[lang]) {
        Object.assign(I18N[lang], I18N_BUILTIN[lang]);
      }
      resolve();
    };
    s.onerror = () => {
      // Fallback: if requested lang fails and isn't 'en'/'zh', resolve anyway
      resolve();
    };
    document.head.appendChild(s);
  });
}

function t(key, params) {
  const lang = (window.app && window.app.lang) ? window.app.lang : "zh";
  const cur = I18N[lang];
  let res = (cur && cur[key])
    || (I18N.en && I18N.en[key])
    || (I18N.zh && I18N.zh[key])
    || (I18N_BUILTIN[lang] && I18N_BUILTIN[lang][key])
    || (I18N_BUILTIN.en && I18N_BUILTIN.en[key])
    || (I18N_BUILTIN.zh && I18N_BUILTIN.zh[key])
    || key;
  if (params && typeof res === "string") {
    for (const [k, v] of Object.entries(params)) {
      res = res.replace(new RegExp(`\\{${k}\\}`, "g"), v);
    }
  }
  return res;
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
