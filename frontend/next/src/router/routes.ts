import type { RouteRecordRaw } from "vue-router";
import AppShell from "@/components/AppShell.vue";
import GalleryDetailView from "@/views/gallery/GalleryDetailView.vue";
import LoginView from "@/views/LoginView.vue";
import PlaceholderView from "@/views/PlaceholderView.vue";
import BrowseView from "@/views/browse/BrowseView.vue";
import LibraryView from "@/views/library/LibraryView.vue";
import ReaderView from "@/views/reader/ReaderView.vue";

/**
 * Hash-mode route table (legacy bookmarks keep working).
 *
 * The old frontend parsed `#/view[/id[/page]][?k=v]`; aliases from core.js are
 * preserved here. Pages not migrated yet render PlaceholderView. `#/series/{id}`
 * is a dead legacy route and redirects to the series list (parity/waivers.json).
 */
export const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: LoginView,
    meta: { public: true, title: "login.subtitle" },
  },
  {
    path: "/",
    component: AppShell,
    children: [
      { path: "", redirect: "/browse" },
      {
        path: "browse",
        name: "browse",
        component: BrowseView,
        meta: { title: "app.nav.browse" },
      },
      {
        path: "online",
        alias: ["/discover"],
        name: "online",
        component: PlaceholderView,
        meta: { title: "app.nav.online" },
      },
      {
        path: "online/g/:gid/:token",
        name: "online-detail",
        component: PlaceholderView,
        meta: { title: "app.nav.online" },
      },
      {
        path: "online/g/:gid/:token/read/:page",
        name: "online-reader",
        component: PlaceholderView,
        meta: { title: "app.nav.online" },
      },
      {
        path: "library",
        name: "library",
        component: LibraryView,
        meta: { title: "app.nav.library" },
      },
      {
        path: "gallery/:id",
        name: "gallery",
        component: GalleryDetailView,
        meta: { title: "app.nav.library" },
      },
      {
        path: "reader/:id/:page",
        name: "reader",
        component: ReaderView,
        meta: { title: "app.nav.library" },
      },
      {
        path: "series",
        name: "series",
        component: PlaceholderView,
        meta: { title: "app.nav.series" },
      },
      {
        path: "series/:id",
        redirect: "/series",
      },
      {
        path: "tags",
        name: "tags",
        component: PlaceholderView,
        meta: { title: "app.nav.tags" },
      },
      {
        path: "history",
        name: "history",
        component: PlaceholderView,
        meta: { title: "app.nav.history" },
      },
      {
        path: "downloads",
        name: "downloads",
        component: PlaceholderView,
        meta: { title: "app.nav.downloads" },
      },
      {
        path: "logs",
        name: "logs",
        component: PlaceholderView,
        meta: { title: "app.nav.logs" },
      },
      {
        path: "settings",
        name: "settings",
        component: PlaceholderView,
        meta: { title: "app.nav.settings" },
      },
      {
        path: "favorites",
        name: "favorites",
        component: PlaceholderView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "favorites/manage",
        alias: ["/duplicates/favorites"],
        name: "favorites-manage",
        component: PlaceholderView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "favorites/ignored",
        name: "favorites-ignored",
        component: PlaceholderView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "favorites/:id",
        name: "favorites-list",
        component: PlaceholderView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "duplicates",
        name: "duplicates",
        component: PlaceholderView,
        meta: { title: "app.nav.duplicates" },
      },
      {
        path: "duplicates/cross-gid",
        name: "duplicates-cross-gid",
        component: PlaceholderView,
        meta: { title: "app.nav.duplicates" },
      },
      {
        path: "updates",
        name: "updates",
        component: PlaceholderView,
        meta: { title: "app.nav.updates" },
      },
      {
        path: "updates/ignored",
        name: "updates-ignored",
        component: PlaceholderView,
        meta: { title: "app.nav.updates" },
      },
      {
        path: "recycle",
        name: "recycle",
        component: PlaceholderView,
        meta: { title: "app.nav.recycle" },
      },
      {
        path: "integrity",
        name: "integrity",
        component: PlaceholderView,
        meta: { title: "app.nav.integrity" },
      },
      {
        path: "archive",
        name: "archive",
        component: PlaceholderView,
        meta: { title: "app.nav.archive" },
      },
      {
        path: "welcome",
        name: "welcome",
        component: PlaceholderView,
        meta: { title: "app.title" },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/browse" },
];
