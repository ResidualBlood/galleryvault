import type { RouteRecordRaw } from "vue-router";
import AppShell from "@/components/AppShell.vue";
import GalleryDetailView from "@/views/gallery/GalleryDetailView.vue";
import LoginView from "@/views/LoginView.vue";
import BrowseView from "@/views/browse/BrowseView.vue";
import DuplicatesView from "@/views/duplicates/DuplicatesView.vue";
import CrossGidView from "@/views/duplicates/CrossGidView.vue";
import FavoriteDuplicatesView from "@/views/duplicates/FavoriteDuplicatesView.vue";
import FavoriteDuplicatesIgnoredView from "@/views/duplicates/FavoriteDuplicatesIgnoredView.vue";
import IntegrityView from "@/views/integrity/IntegrityView.vue";
import RecycleView from "@/views/recycle/RecycleView.vue";
import UpdatesView from "@/views/updates/UpdatesView.vue";
import UpdatesIgnoredView from "@/views/updates/UpdatesIgnoredView.vue";
import LibraryView from "@/views/library/LibraryView.vue";
import OnlineDetailView from "@/views/online/detail/OnlineDetailView.vue";
import OnlineListView from "@/views/online/list/OnlineListView.vue";
import OnlineReaderView from "@/views/online/reader/OnlineReaderView.vue";
import ReaderView from "@/views/reader/ReaderView.vue";
import SeriesView from "@/views/series/SeriesView.vue";
import TagsView from "@/views/tags/TagsView.vue";
import FavoritesView from "@/views/favorites/FavoritesView.vue";
import FavListView from "@/views/favorites/FavListView.vue";
import DownloadsView from "@/views/downloads/DownloadsView.vue";
import HistoryView from "@/views/history/local/HistoryView.vue";

/**
 * Hash-mode route table (legacy bookmarks keep working).
 *
 * The old frontend parsed `#/view[/id[/page]][?k=v]`; aliases from core.js are
 * preserved here. `#/series/{id}`
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
        component: OnlineListView,
        meta: { title: "app.nav.online" },
      },
      {
        path: "online/g/:gid/:token",
        name: "online-detail",
        component: OnlineDetailView,
        meta: { title: "app.nav.online" },
      },
      {
        path: "online/g/:gid/:token/read/:page",
        name: "online-reader",
        component: OnlineReaderView,
        // RD-08: readers are a fixed overlay; the shell renders no bars and
        // the document must not scroll behind them.
        meta: { title: "app.nav.online", immersive: true },
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
        meta: { title: "app.nav.library", immersive: true },
      },
      {
        path: "series",
        name: "series",
        component: SeriesView,
        meta: { title: "app.nav.series" },
      },
      {
        path: "series/:id",
        redirect: "/series",
      },
      {
        path: "tags",
        name: "tags",
        component: TagsView,
        meta: { title: "app.nav.tags" },
      },
      {
        path: "history",
        name: "history",
        component: HistoryView,
        meta: { title: "app.nav.history" },
      },
      {
        path: "downloads",
        name: "downloads",
        component: DownloadsView,
        meta: { title: "app.nav.downloads" },
      },
      {
        path: "logs",
        name: "logs",
        component: () => import("@/views/logs/LogsView.vue"),
        meta: { title: "app.nav.logs" },
      },
      {
        path: "settings",
        name: "settings",
        component: () => import("@/views/settings/SettingsView.vue"),
        meta: { title: "app.nav.settings" },
      },
      {
        path: "favorites",
        name: "favorites",
        component: FavoritesView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "favorites/manage",
        alias: ["/duplicates/favorites"],
        name: "favorites-manage",
        component: FavoriteDuplicatesView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "favorites/ignored",
        name: "favorites-ignored",
        component: FavoriteDuplicatesIgnoredView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "favorites/:id",
        name: "favorites-list",
        component: FavListView,
        meta: { title: "app.nav.favorites" },
      },
      {
        path: "duplicates",
        name: "duplicates",
        component: DuplicatesView,
        meta: { title: "app.nav.duplicates" },
      },
      {
        path: "duplicates/cross-gid",
        name: "duplicates-cross-gid",
        component: CrossGidView,
        meta: { title: "app.nav.duplicates" },
      },
      {
        path: "updates",
        name: "updates",
        component: UpdatesView,
        meta: { title: "app.nav.updates" },
      },
      {
        path: "updates/ignored",
        name: "updates-ignored",
        component: UpdatesIgnoredView,
        meta: { title: "app.nav.updates" },
      },
      {
        path: "recycle",
        name: "recycle",
        component: RecycleView,
        meta: { title: "app.nav.recycle" },
      },
      {
        path: "integrity",
        name: "integrity",
        component: IntegrityView,
        meta: { title: "app.nav.integrity" },
      },
      {
        path: "archive",
        name: "archive",
        component: () => import("@/views/archive/ArchiveView.vue"),
        meta: { title: "app.nav.archive" },
      },
      {
        path: "_kit",
        name: "kit",
        component: () => import("@/views/kit/KitView.vue"),
        meta: { title: "app.title" },
      },
      {
        path: "welcome",
        name: "welcome",
        component: () => import("@/views/welcome/WelcomeView.vue"),
        meta: { title: "app.title" },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/browse" },
];
