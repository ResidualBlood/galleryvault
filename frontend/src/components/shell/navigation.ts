import type { IconName } from "@/components/icons/registry";

/**
 * Single source of truth for the 15 navigation destinations.
 *
 * The drawer, rail, bottom bar and the mobile sheet all render from this table,
 * so a destination can never be reachable at one breakpoint and missing at
 * another (audit SH-02 / SH-04). The order is frozen by the route table; only
 * the presentation changes per breakpoint.
 */
export interface NavDestination {
  to: string;
  labelKey: string;
  icon: IconName;
}

export interface NavGroup {
  id: "primary" | "more" | "manage";
  /** Heading above the group in the drawer / sheet; the primary group has none. */
  headingKey?: string;
  items: NavDestination[];
}

export const navGroups: NavGroup[] = [
  {
    id: "primary",
    items: [
      { to: "/browse", labelKey: "app.nav.browse", icon: "browse" },
      { to: "/online", labelKey: "app.nav.online", icon: "online" },
      { to: "/library", labelKey: "app.nav.library", icon: "library" },
      { to: "/favorites", labelKey: "app.nav.favorites", icon: "favorites" },
      { to: "/downloads", labelKey: "app.nav.downloads", icon: "downloads" },
    ],
  },
  {
    id: "more",
    headingKey: "app.nav.more",
    items: [
      { to: "/series", labelKey: "app.nav.series", icon: "series" },
      { to: "/tags", labelKey: "app.nav.tags", icon: "tags" },
      { to: "/history", labelKey: "app.nav.history", icon: "history" },
    ],
  },
  {
    id: "manage",
    headingKey: "app.nav.manage",
    items: [
      { to: "/updates", labelKey: "app.nav.updates", icon: "updates" },
      { to: "/duplicates", labelKey: "app.nav.duplicates", icon: "duplicates" },
      { to: "/recycle", labelKey: "app.nav.recycle", icon: "recycle" },
      { to: "/integrity", labelKey: "app.nav.integrity", icon: "integrity" },
      { to: "/archive", labelKey: "app.nav.archive", icon: "archive" },
    ],
  },
];

/** Pinned at the bottom of the drawer / sheet, never scrolled out of reach. */
export const navFixed: NavDestination[] = [
  { to: "/settings", labelKey: "app.nav.settings", icon: "settings" },
  { to: "/logs", labelKey: "app.nav.logs", icon: "logs" },
];

/** All 15 destinations, in the order the navigation renders them. */
export const navDestinations: NavDestination[] = [
  ...navGroups.flatMap((group) => group.items),
  ...navFixed,
];

/** Grouped destinations without the pinned footer (drawer scroll area / rail). */
export const navScrollable: NavDestination[] = navGroups.flatMap((group) => group.items);

/** Bottom bar: the first four primary destinations plus a "more" entry. */
export const bottomDestinations: NavDestination[] = navGroups[0].items.slice(0, 4);
