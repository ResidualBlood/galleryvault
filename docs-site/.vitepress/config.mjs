import { defineConfig } from "vitepress";

export default defineConfig({
  title: "GalleryVault",
  description:
    "Private, self-hosted gallery library manager with ExHentai integration.",
  lang: "zh-CN",
  base: "/galleryvault/",
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,

  themeConfig: {
    nav: [
      { text: "首页", link: "/" },
      {
        text: "开始",
        items: [
          { text: "入门 (Usage)", link: "/Usage" },
          { text: "功能特性 (Features)", link: "/Features" },
          { text: "兼容格式 (Compatibility)", link: "/Compatibility" },
          { text: "界面截图 (Screenshots)", link: "/Screenshots" },
        ],
      },
      {
        text: "使用",
        items: [
          { text: "浏览与库 (Library)", link: "/Library" },
          { text: "阅读 (Reading)", link: "/Reading" },
          { text: "下载 (Downloads)", link: "/Downloads" },
          { text: "收藏与更新 (Favorites)", link: "/Favorites" },
          { text: "库维护 (Manage)", link: "/Manage" },
          { text: "设置 (Settings)", link: "/Settings" },
        ],
      },
      {
        text: "运维",
        items: [
          { text: "部署 (Deployment)", link: "/Deployment" },
          { text: "备份与恢复 (Backup)", link: "/Backup" },
          { text: "静态加密 (Encryption)", link: "/Encryption" },
          { text: "常见问题 (FAQ)", link: "/FAQ" },
        ],
      },
      {
        text: "开发",
        items: [
          { text: "API 参考", link: "/API" },
          { text: "开发指南", link: "/Development" },
        ],
      },
      { text: "English", link: "/Home-EN" },
      { text: "GitHub", link: "https://github.com/ResidualBlood/galleryvault" },
    ],
    sidebar: [
      {
        text: "📖 GalleryVault",
        collapsed: false,
        items: [
          { text: "首页", link: "/Home" },
          { text: "Home (EN)", link: "/Home-EN" },
        ],
      },
      {
        text: "开始",
        collapsed: false,
        items: [
          { text: "入门", link: "/Usage" },
          { text: "Usage (EN)", link: "/Usage-EN" },
          { text: "功能特性", link: "/Features" },
          { text: "Features (EN)", link: "/Features-EN" },
          { text: "兼容格式", link: "/Compatibility" },
          { text: "Compatibility (EN)", link: "/Compatibility-EN" },
          { text: "界面截图", link: "/Screenshots" },
          { text: "Screenshots (EN)", link: "/Screenshots-EN" },
        ],
      },
      {
        text: "使用",
        collapsed: false,
        items: [
          { text: "浏览与库", link: "/Library" },
          { text: "Library (EN)", link: "/Library-EN" },
          { text: "阅读", link: "/Reading" },
          { text: "Reading (EN)", link: "/Reading-EN" },
          { text: "下载", link: "/Downloads" },
          { text: "Downloads (EN)", link: "/Downloads-EN" },
          { text: "收藏与更新", link: "/Favorites" },
          { text: "Favorites (EN)", link: "/Favorites-EN" },
          { text: "库维护", link: "/Manage" },
          { text: "Manage (EN)", link: "/Manage-EN" },
          { text: "设置", link: "/Settings" },
          { text: "Settings (EN)", link: "/Settings-EN" },
        ],
      },
      {
        text: "运维",
        collapsed: false,
        items: [
          { text: "部署", link: "/Deployment" },
          { text: "Deployment (EN)", link: "/Deployment-EN" },
          { text: "备份与恢复", link: "/Backup" },
          { text: "Backup (EN)", link: "/Backup-EN" },
          { text: "静态加密", link: "/Encryption" },
          { text: "Encryption (EN)", link: "/Encryption-EN" },
          { text: "常见问题", link: "/FAQ" },
          { text: "FAQ (EN)", link: "/FAQ-EN" },
        ],
      },
      {
        text: "开发",
        collapsed: false,
        items: [
          { text: "API 参考", link: "/API" },
          { text: "开发指南", link: "/Development" },
        ],
      },
    ],
    outline: { label: "本页目录", level: [2, 3] },
    docFooter: {
      prev: "上一页",
      next: "下一页",
    },
    lastUpdated: { text: "最后更新" },
    editLink: {
      pattern:
        "https://github.com/ResidualBlood/galleryvault/edit/main/docs/wiki/:path",
      text: "在 GitHub 上编辑此页",
    },
  },
});
