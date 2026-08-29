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
      { text: "使用指南", link: "/Usage" },
      { text: "部署", link: "/Deployment" },
      { text: "API", link: "/API" },
      { text: "FAQ", link: "/FAQ" },
      { text: "English", link: "/Home-EN" },
      { text: "GitHub", link: "https://github.com/ResidualBlood/galleryvault" },
    ],
    sidebar: [
      {
        text: "中文",
        collapsed: false,
        items: [
          { text: "首页", link: "/Home" },
          { text: "使用指南", link: "/Usage" },
          { text: "部署", link: "/Deployment" },
          { text: "备份与恢复", link: "/Backup" },
          { text: "静态加密", link: "/Encryption" },
          { text: "常见问题", link: "/FAQ" },
          { text: "界面截图", link: "/Screenshots" },
          { text: "API 参考", link: "/API" },
          { text: "开发指南", link: "/Development" },
        ],
      },
      {
        text: "English",
        collapsed: false,
        items: [
          { text: "Home", link: "/Home-EN" },
          { text: "Usage", link: "/Usage-EN" },
          { text: "Deployment", link: "/Deployment-EN" },
          { text: "Backup", link: "/Backup-EN" },
          { text: "Encryption", link: "/Encryption-EN" },
          { text: "FAQ", link: "/FAQ-EN" },
          { text: "Screenshots", link: "/Screenshots-EN" },
          { text: "API", link: "/API" },
          { text: "Development", link: "/Development" },
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
