<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import IconButton from "@/components/ui/IconButton.vue";
import Popover from "@/components/ui/Popover.vue";
import LangToggle from "@/components/LangToggle.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";
import CookieHealthBanner from "@/components/system/CookieHealthBanner.vue";
import GlobalControls from "@/components/system/GlobalControls.vue";
import NotificationPanel from "@/components/system/NotificationPanel.vue";
import { ensureSystemMessages } from "@/components/system/messages";
import { useAuthStore } from "@/stores/auth";

// The shell owns the notification / cookie / global widgets, so it registers
// their `system` namespace on first mount (views do the same for standalone use).
ensureSystemMessages();

interface NavItem {
  to: string;
  labelKey: string;
  glyph: string;
}

const primary: NavItem[] = [
  { to: "/browse", labelKey: "app.nav.browse", glyph: "▦" },
  { to: "/online", labelKey: "app.nav.online", glyph: "◉" },
  { to: "/library", labelKey: "app.nav.library", glyph: "▤" },
  { to: "/favorites", labelKey: "app.nav.favorites", glyph: "♥" },
  { to: "/downloads", labelKey: "app.nav.downloads", glyph: "⇩" },
];

const more: NavItem[] = [
  { to: "/series", labelKey: "app.nav.series", glyph: "≡" },
  { to: "/tags", labelKey: "app.nav.tags", glyph: "#" },
  { to: "/history", labelKey: "app.nav.history", glyph: "↺" },
];

const manage: NavItem[] = [
  { to: "/updates", labelKey: "app.nav.updates", glyph: "↑" },
  { to: "/duplicates", labelKey: "app.nav.duplicates", glyph: "⧉" },
  { to: "/recycle", labelKey: "app.nav.recycle", glyph: "♻" },
  { to: "/integrity", labelKey: "app.nav.integrity", glyph: "✓" },
  { to: "/archive", labelKey: "app.nav.archive", glyph: "⛁" },
];

const fixed: NavItem[] = [
  { to: "/settings", labelKey: "app.nav.settings", glyph: "⚙" },
  { to: "/logs", labelKey: "app.nav.logs", glyph: "≣" },
];

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { t } = useI18n();
const drawerOpen = ref(true);

/**
 * G-07: the session probe already reports the cookie state (same source as the
 * legacy shell), so only ask for the detailed health when it is not `ok`.
 */
const showCookieBanner = computed(() => {
  const state = auth.session?.cookie_health?.state;
  return Boolean(state) && state !== "ok";
});

const pageTitle = computed(() => {
  const meta = route.meta.title;
  return t(typeof meta === "string" ? meta : "app.title");
});

async function signOut(): Promise<void> {
  await auth.logout();
  await router.replace({ name: "login" });
}
</script>

<template>
  <div class="shell">
    <CookieHealthBanner v-if="showCookieBanner" />

    <header class="shell__topbar">
      <IconButton
        class="shell__menu"
        :label="t('app.actions.menu')"
        data-testid="drawer-toggle"
        @click="drawerOpen = !drawerOpen"
      >
        <span aria-hidden="true">☰</span>
      </IconButton>
      <RouterLink to="/browse" class="shell__brand">{{ t("app.title") }}</RouterLink>
      <span class="shell__page-title">{{ pageTitle }}</span>
      <span class="shell__spacer" />
      <Popover align="end">
        <template #trigger>
          <IconButton :label="t('app.actions.notifications')" data-testid="notifications">
            <span aria-hidden="true">◔</span>
          </IconButton>
        </template>
        <NotificationPanel :poll-ms="0" />
      </Popover>
      <Popover align="end">
        <template #trigger>
          <IconButton
            :label="t('system.global.controls')"
            data-testid="global-controls-toggle"
          >
            <span aria-hidden="true">⏯</span>
          </IconButton>
        </template>
        <GlobalControls class="shell__controls-popover" />
      </Popover>
      <ThemeToggle />
      <LangToggle />
      <IconButton :label="t('app.actions.logout')" data-testid="logout" @click="signOut">
        <span aria-hidden="true">⏻</span>
      </IconButton>
    </header>

    <div class="shell__body">
      <aside class="shell__rail" data-testid="nav-rail" :aria-label="t('app.actions.menu')">
        <RouterLink
          v-for="item in primary"
          :key="item.to"
          :to="item.to"
          class="rail-item"
          :data-nav="item.labelKey"
        >
          <span class="rail-item__glyph" aria-hidden="true">{{ item.glyph }}</span>
          <span class="rail-item__label">{{ t(item.labelKey) }}</span>
        </RouterLink>
      </aside>

      <aside
        class="shell__drawer"
        :class="{ 'shell__drawer--closed': !drawerOpen }"
        data-testid="nav-drawer"
      >
        <div class="drawer__inner">
          <RouterLink to="/browse" class="drawer__brand">{{ t("app.title") }}</RouterLink>
          <nav class="drawer__group">
            <RouterLink
              v-for="item in primary"
              :key="item.to"
              :to="item.to"
              class="nav-item"
              :data-nav="item.labelKey"
            >
              <span class="nav-item__glyph" aria-hidden="true">{{ item.glyph }}</span>
              <span>{{ t(item.labelKey) }}</span>
            </RouterLink>
          </nav>
          <p class="drawer__heading">{{ t("app.nav.more") }}</p>
          <nav class="drawer__group">
            <RouterLink
              v-for="item in more"
              :key="item.to"
              :to="item.to"
              class="nav-item"
              :data-nav="item.labelKey"
            >
              <span class="nav-item__glyph" aria-hidden="true">{{ item.glyph }}</span>
              <span>{{ t(item.labelKey) }}</span>
            </RouterLink>
          </nav>
          <p class="drawer__heading">{{ t("app.nav.manage") }}</p>
          <nav class="drawer__group">
            <RouterLink
              v-for="item in manage"
              :key="item.to"
              :to="item.to"
              class="nav-item"
              :data-nav="item.labelKey"
            >
              <span class="nav-item__glyph" aria-hidden="true">{{ item.glyph }}</span>
              <span>{{ t(item.labelKey) }}</span>
            </RouterLink>
          </nav>
        </div>
        <nav class="drawer__group drawer__group--fixed">
          <RouterLink
            v-for="item in fixed"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :data-nav="item.labelKey"
          >
            <span class="nav-item__glyph" aria-hidden="true">{{ item.glyph }}</span>
            <span>{{ t(item.labelKey) }}</span>
          </RouterLink>
        </nav>
      </aside>

      <main class="shell__content" data-testid="content">
        <RouterView />
      </main>
    </div>

    <nav class="shell__bottom" data-testid="nav-bottom" :aria-label="t('app.actions.menu')">
      <RouterLink
        v-for="item in primary"
        :key="item.to"
        :to="item.to"
        class="bottom-item"
        :data-nav="item.labelKey"
      >
        <span class="bottom-item__glyph" aria-hidden="true">{{ item.glyph }}</span>
        <span class="bottom-item__label">{{ t(item.labelKey) }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at 15% 0, var(--gv-color-primary-container) 0, transparent 34%),
    var(--gv-color-background);
  color: var(--gv-color-on-background);
}

.shell__topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--gv-space-1);
  height: var(--gv-size-topbar);
  padding: 0 var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: color-mix(in srgb, var(--gv-color-surface-container) 94%, transparent);
  backdrop-filter: blur(8px);
}

.shell__menu {
  display: none;
}

.shell__brand {
  display: none;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-primary-text);
}

.shell__page-title {
  overflow: hidden;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shell__spacer {
  flex: 1;
}

.shell__controls-popover {
  width: min(360px, calc(100vw - var(--gv-space-6)));
}

.shell__body {
  display: flex;
  min-height: calc(100vh - var(--gv-size-topbar));
}

.shell__rail {
  display: none;
  flex: 0 0 var(--gv-size-rail-width);
  flex-direction: column;
  gap: var(--gv-space-1);
  padding: var(--gv-space-2) 0;
  border-inline-end: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container-low);
}

.shell__drawer {
  display: none;
  flex: 0 0 var(--gv-size-drawer-width);
  width: var(--gv-size-drawer-width);
  flex-direction: column;
  justify-content: space-between;
  padding: var(--gv-space-3) 0;
  border-inline-end: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container-low);
  overflow: hidden;
  transition:
    width var(--gv-motion-duration-medium) var(--gv-motion-ease-standard),
    flex-basis var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.shell__drawer--closed {
  flex-basis: 0;
  width: 0;
  border-inline-end: 0;
}

.drawer__inner {
  display: flex;
  flex-direction: column;
}

.drawer__brand {
  padding: 0 var(--gv-space-5);
  margin-bottom: var(--gv-space-3);
  font: var(--gv-type-title-large);
  color: var(--gv-color-primary-text);
}

.drawer__heading {
  margin: var(--gv-space-4) 0 var(--gv-space-1);
  padding: 0 var(--gv-space-5);
  font: var(--gv-type-label-large);
  color: var(--gv-color-primary-text);
}

.drawer__group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.drawer__group--fixed {
  margin-top: auto;
}

.nav-item,
.rail-item,
.bottom-item {
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  min-height: 48px;
  margin: 0 var(--gv-space-2);
  padding: 0 var(--gv-space-3);
  border-radius: var(--gv-radius-full);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-large);
}

.nav-item__glyph,
.rail-item__glyph,
.bottom-item__glyph {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--gv-size-icon-lg);
  font: var(--gv-type-title-medium);
}

.nav-item:hover,
.rail-item:hover,
.bottom-item:hover {
  background: color-mix(in srgb, var(--gv-color-on-surface) 8%, transparent);
}

.nav-item.router-link-active,
.rail-item.router-link-active,
.bottom-item.router-link-active {
  background: var(--gv-color-secondary-container);
  color: var(--gv-color-on-secondary-container);
}

.rail-item {
  flex-direction: column;
  gap: var(--gv-space-1);
  min-height: 56px;
  margin: 0 var(--gv-space-1);
  padding: var(--gv-space-1) 0;
  border-radius: var(--gv-radius-md);
}

.rail-item__label {
  font: var(--gv-type-label-small);
  text-align: center;
}

.shell__content {
  flex: 1;
  width: 100%;
  max-width: var(--gv-size-content-max);
  min-width: 0;
  margin: 0 auto;
  padding: var(--gv-space-4);
  padding-bottom: calc(var(--gv-size-navbar) + var(--gv-space-4));
}

.shell__bottom {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 20;
  display: flex;
  justify-content: space-around;
  height: var(--gv-size-navbar);
  border-top: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container);
}

.bottom-item {
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: var(--gv-space-1);
  margin: var(--gv-space-1) 0;
  padding: 0;
  border-radius: var(--gv-radius-md);
}

.bottom-item__label {
  font: var(--gv-type-label-small);
}

/* --gv-bp-compact = 600px */
@media (min-width: 600px) {
  .shell__topbar {
    padding: 0 var(--gv-space-4);
  }

  .shell__brand {
    display: inline;
  }

  .shell__rail {
    display: flex;
  }

  .shell__bottom {
    display: none;
  }

  .shell__content {
    padding: var(--gv-space-5);
    padding-bottom: var(--gv-space-5);
  }
}

/* --gv-bp-medium = 840px */
@media (min-width: 840px) {
  .shell__menu {
    display: inline-flex;
  }

  .shell__rail {
    display: none;
  }

  .shell__drawer {
    display: flex;
  }
}

@media (prefers-reduced-motion: reduce) {
  .shell__drawer {
    transition-duration: 1ms;
  }
}
</style>
