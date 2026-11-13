<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Icon from "@/components/icons/Icon.vue";
import Button from "@/components/ui/Button.vue";
import IconButton from "@/components/ui/IconButton.vue";
import Popover from "@/components/ui/Popover.vue";
import LangToggle from "@/components/LangToggle.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";
import CookieHealthBanner from "@/components/system/CookieHealthBanner.vue";
import GlobalControls from "@/components/system/GlobalControls.vue";
import NotificationPanel from "@/components/system/NotificationPanel.vue";
import { ensureSystemMessages } from "@/components/system/messages";
import NavLink from "@/components/shell/NavLink.vue";
import NavSheet from "@/components/shell/NavSheet.vue";
import {
  bottomDestinations,
  navFixed,
  navGroups,
  navScrollable,
} from "@/components/shell/navigation";
import { useAuthStore } from "@/stores/auth";

// The shell owns the notification / cookie / global widgets, so it registers
// their `system` namespace on first mount (views do the same for standalone use).
ensureSystemMessages();

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { t } = useI18n();

/** >= 840px keeps the persistent drawer and the full topbar action row. */
const wide = ref(
  typeof window === "undefined" ? true : window.matchMedia("(min-width: 840px)").matches,
);
let media: MediaQueryList | null = null;

function onMediaChange(event: MediaQueryListEvent): void {
  wide.value = event.matches;
}

const drawerOpen = ref(true);
const sheetOpen = ref(false);

/** Reader routes render their own chrome: no shell bars, no shell padding. */
const immersive = computed(() => Boolean(route.meta.immersive));

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

/**
 * SH-03: the welcome / kit routes use the app title as their page title, which
 * printed "GalleryVault GalleryVault" in the topbar. Show the brand once.
 */
const showPageTitle = computed(() => pageTitle.value !== t("app.title"));

const globalControlsLabel = computed(
  () =>
    `${t("system.global.controls")}: ${t("system.global.pause")} / ${t("system.global.scan")}`,
);

function toggleNav(): void {
  if (wide.value) drawerOpen.value = !drawerOpen.value;
  else sheetOpen.value = true;
}

function openSheet(): void {
  sheetOpen.value = true;
}

async function signOut(): Promise<void> {
  sheetOpen.value = false;
  await auth.logout();
  await router.replace({ name: "login" });
}

watch(wide, (value) => {
  if (value) sheetOpen.value = false;
  else drawerOpen.value = true;
});

// Navigating always closes the mobile sheet, including browser back/forward.
watch(
  () => route.fullPath,
  () => {
    sheetOpen.value = false;
  },
);

// RD-08: the reader is a fixed overlay; the document behind it must not scroll.
watch(
  immersive,
  (value) => document.documentElement.classList.toggle("gv-shell-immersive", value),
  { immediate: true },
);

onMounted(() => {
  media = window.matchMedia("(min-width: 840px)");
  wide.value = media.matches;
  media.addEventListener("change", onMediaChange);
});

onBeforeUnmount(() => {
  media?.removeEventListener("change", onMediaChange);
  document.documentElement.classList.remove("gv-shell-immersive");
});
</script>

<template>
  <div class="shell" :class="{ 'shell--immersive': immersive }">
    <CookieHealthBanner v-if="showCookieBanner && !immersive" />

    <header v-if="!immersive" class="shell__topbar" data-testid="topbar">
      <IconButton
        class="shell__menu"
        :label="t('app.actions.menu')"
        data-testid="drawer-toggle"
        @click="toggleNav"
      >
        <Icon name="menu" size="md" />
      </IconButton>
      <RouterLink to="/browse" class="shell__brand">{{ t("app.title") }}</RouterLink>
      <template v-if="showPageTitle">
        <span class="shell__divider" aria-hidden="true" />
        <span class="shell__page-title">{{ pageTitle }}</span>
      </template>
      <span class="shell__spacer" />
      <div class="shell__actions">
        <span class="shell__divider shell__divider--actions" aria-hidden="true" />
        <Popover align="end">
          <template #trigger>
            <IconButton :label="t('app.actions.notifications')" data-testid="notifications">
              <Icon name="notifications" size="md" />
            </IconButton>
          </template>
          <NotificationPanel :poll-ms="0" />
        </Popover>
        <Popover align="end">
          <template #trigger>
            <IconButton :label="globalControlsLabel" data-testid="global-controls-toggle">
              <Icon name="global-controls" size="md" />
            </IconButton>
          </template>
          <GlobalControls class="shell__controls-popover" />
        </Popover>
        <template v-if="wide">
          <span class="shell__divider shell__divider--actions" aria-hidden="true" />
          <ThemeToggle />
          <LangToggle />
          <IconButton :label="t('app.actions.logout')" data-testid="logout" @click="signOut">
            <Icon name="logout" size="md" />
          </IconButton>
        </template>
      </div>
    </header>

    <div v-if="!immersive" class="shell__body">
      <aside class="shell__rail" data-testid="nav-rail" :aria-label="t('app.nav.aria')">
        <div class="rail__scroll">
          <nav class="rail__group" :aria-label="t('app.nav.aria')">
            <NavLink
              v-for="item in navScrollable"
              :key="item.to"
              :item="item"
              variant="rail"
            />
          </nav>
        </div>
        <nav class="rail__group rail__group--fixed" :aria-label="t('app.nav.aria')">
          <NavLink v-for="item in navFixed" :key="item.to" :item="item" variant="rail" />
        </nav>
      </aside>

      <aside
        class="shell__drawer"
        :class="{ 'shell__drawer--closed': !drawerOpen }"
        data-testid="nav-drawer"
      >
        <div class="drawer__scroll">
          <RouterLink to="/browse" class="drawer__brand">{{ t("app.title") }}</RouterLink>
          <nav
            v-for="group in navGroups"
            :key="group.id"
            class="drawer__group"
            :aria-label="group.headingKey ? t(group.headingKey) : t('app.nav.aria')"
          >
            <p v-if="group.headingKey" class="drawer__heading">{{ t(group.headingKey) }}</p>
            <NavLink v-for="item in group.items" :key="item.to" :item="item" />
          </nav>
        </div>
        <nav class="drawer__group drawer__group--fixed" :aria-label="t('app.nav.aria')">
          <NavLink v-for="item in navFixed" :key="item.to" :item="item" />
        </nav>
      </aside>

      <main class="shell__content" data-testid="content">
        <RouterView />
      </main>
    </div>

    <main v-else class="shell__content shell__content--immersive" data-testid="content">
      <RouterView />
    </main>

    <nav
      v-if="!immersive"
      class="shell__bottom"
      data-testid="nav-bottom"
      :aria-label="t('app.nav.aria')"
    >
      <NavLink
        v-for="item in bottomDestinations"
        :key="item.to"
        :item="item"
        variant="bottom"
      />
      <Button
        class="bottom-item"
        variant="text"
        :aria-label="t('app.nav.more')"
        data-testid="bottom-more"
        @click="openSheet"
      >
        <span class="bottom-item__icon">
          <Icon name="more" size="lg" />
        </span>
        <span class="bottom-item__label">{{ t("app.nav.more") }}</span>
      </Button>
    </nav>

    <NavSheet v-if="!wide && !immersive" :open="sheetOpen" @close="sheetOpen = false">
      <template #account>
        <ThemeToggle />
        <LangToggle />
        <IconButton :label="t('app.actions.logout')" data-testid="logout" @click="signOut">
          <Icon name="logout" size="md" />
        </IconButton>
      </template>
    </NavSheet>
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

/* RD-08: immersive routes (readers) own the viewport; nothing behind scrolls. */
.shell--immersive {
  height: 100vh;
  overflow: hidden;
}

:global(html.gv-shell-immersive),
:global(html.gv-shell-immersive body) {
  overflow: hidden;
}

.shell__topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--gv-space-3);
  height: var(--gv-size-topbar);
  padding: 0 var(--gv-space-3);
  border-bottom: 1px solid var(--gv-color-outline-variant);
  background: color-mix(in srgb, var(--gv-color-surface-container) 94%, transparent);
  backdrop-filter: blur(8px);
}

.shell__menu {
  flex: none;
}

.shell__brand {
  display: none;
  flex: none;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-primary-text);
}

.shell__divider {
  display: none;
  flex: none;
  width: 1px;
  height: 20px;
  background: var(--gv-color-outline-variant);
}

.shell__page-title {
  overflow: hidden;
  min-width: 0;
  font: var(--gv-type-title-medium);
  color: var(--gv-color-on-surface);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shell__spacer {
  flex: 1;
}

.shell__actions {
  display: flex;
  flex: none;
  align-items: center;
  /* The 40px icon buttons expand their hit area to 44px (2px per side), so the
     row gap must clear that overhang; otherwise the next button paints over the
     touch target. 8px = DESIGN.md C12 组内间距 and leaves 4px between targets. */
  gap: var(--gv-space-2);
}

.shell__divider--actions {
  display: block;
  height: 24px;
  margin: 0 var(--gv-space-1);
}

.shell__controls-popover {
  /* Wide enough for the three global actions on one row (audit: one control
     ladder step per toolbar, centre lines within 1px). */
  width: min(480px, calc(100vw - var(--gv-space-6)));
}

.shell__body {
  display: flex;
  min-height: calc(100vh - var(--gv-size-topbar));
}

.shell__rail {
  position: sticky;
  top: var(--gv-size-topbar);
  display: none;
  flex: 0 0 var(--gv-size-rail-width);
  flex-direction: column;
  align-self: flex-start;
  width: var(--gv-size-rail-width);
  height: calc(100vh - var(--gv-size-topbar));
  overflow: hidden;
  border-inline-end: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container-low);
}

.rail__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--gv-space-2) 0;
}

.rail__group {
  display: flex;
  flex-direction: column;
  gap: var(--gv-space-1);
}

.rail__group--fixed {
  flex: none;
  padding: var(--gv-space-2) 0;
  border-top: 1px solid var(--gv-color-outline-variant);
}

.shell__drawer {
  position: sticky;
  top: var(--gv-size-topbar);
  display: none;
  flex: 0 0 var(--gv-size-drawer-width);
  flex-direction: column;
  align-self: flex-start;
  width: var(--gv-size-drawer-width);
  height: calc(100vh - var(--gv-size-topbar));
  overflow: hidden;
  border-inline-end: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container-low);
  transition:
    width var(--gv-motion-duration-medium) var(--gv-motion-ease-standard),
    flex-basis var(--gv-motion-duration-medium) var(--gv-motion-ease-standard);
}

.shell__drawer--closed {
  flex-basis: 0;
  width: 0;
  border-inline-end: 0;
}

.drawer__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-bottom: var(--gv-space-2);
}

.drawer__brand {
  display: block;
  padding: var(--gv-space-1) var(--gv-space-5) var(--gv-space-2);
  margin-bottom: var(--gv-space-1);
  font: var(--gv-type-title-large);
  color: var(--gv-color-primary-text);
}

.drawer__heading {
  margin: var(--gv-space-3) 0 var(--gv-space-1);
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
  flex: none;
  padding: var(--gv-space-2) 0;
  border-top: 1px solid var(--gv-color-outline-variant);
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

.shell__content--immersive {
  max-width: none;
  height: 100vh;
  padding: 0;
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
  padding: var(--gv-space-1) 0;
  border-top: 1px solid var(--gv-color-outline-variant);
  background: var(--gv-color-surface-container);
}

.bottom-item {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  height: 100%;
  min-height: 0;
  padding: 0;
  border-radius: var(--gv-radius-md);
  color: var(--gv-color-on-surface-variant);
  font: var(--gv-type-label-small);
}

.bottom-item__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 24px;
  border-radius: var(--gv-radius-full);
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

  .shell__divider {
    display: block;
  }

  .shell__rail {
    display: flex;
  }

  .shell__bottom {
    display: none;
  }

  .shell__content {
    padding: var(--gv-space-5);
  }

  .shell__content--immersive {
    padding: 0;
  }
}

/* --gv-bp-medium = 840px */
@media (min-width: 840px) {
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
