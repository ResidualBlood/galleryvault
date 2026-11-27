/**
 * Semantic icon registry.
 *
 * Every icon is imported statically so unplugin-icons can compile it to an
 * inline SVG Vue component at build time. Pages must only reference the
 * semantic names below (`<Icon name="library" />`); nothing outside this
 * directory imports `~icons/` directly. That keeps the icon set swappable and
 * stops ad-hoc glyphs from creeping back into templates.
 *
 * Source: Material Symbols Rounded (Google, Apache-2.0) via
 * `@iconify-json/material-symbols`. Two icons in the set have no `-rounded`
 * variant; the closest same-family icon is used and called out inline.
 */

import BrowseIcon from "~icons/material-symbols/grid-view-rounded";
import OnlineIcon from "~icons/material-symbols/explore-rounded";
import LibraryIcon from "~icons/material-symbols/library-books-rounded";
import FavoritesIcon from "~icons/material-symbols/favorite-rounded";
import DownloadsIcon from "~icons/material-symbols/download-rounded";
import SeriesIcon from "~icons/material-symbols/playlist-play-rounded";
import TagsIcon from "~icons/material-symbols/tag-rounded";
import HistoryIcon from "~icons/material-symbols/history-rounded";
import UpdatesIcon from "~icons/material-symbols/update-rounded";
import DuplicatesIcon from "~icons/material-symbols/difference-rounded";
import RecycleIcon from "~icons/material-symbols/recycling-rounded";
import IntegrityIcon from "~icons/material-symbols/check-circle-rounded";
import ArchiveIcon from "~icons/material-symbols/inventory-2-rounded";
import SettingsIcon from "~icons/material-symbols/settings-rounded";
import LogsIcon from "~icons/material-symbols/subject-rounded";
import MenuIcon from "~icons/material-symbols/menu-rounded";
import NotificationsIcon from "~icons/material-symbols/notifications-rounded";
import GlobalControlsIcon from "~icons/material-symbols/pause-circle-rounded";
import LogoutIcon from "~icons/material-symbols/logout-rounded";
import ThemeLightIcon from "~icons/material-symbols/light-mode-rounded";
import ThemeSystemIcon from "~icons/material-symbols/brightness-auto-rounded";
import ThemeDarkIcon from "~icons/material-symbols/dark-mode-rounded";
import LanguageIcon from "~icons/material-symbols/translate-rounded";

import BackIcon from "~icons/material-symbols/arrow-back-rounded";
import ForwardIcon from "~icons/material-symbols/arrow-forward-rounded";
import FullscreenIcon from "~icons/material-symbols/fullscreen-rounded";
import FirstPageIcon from "~icons/material-symbols/first-page-rounded";
import LastPageIcon from "~icons/material-symbols/last-page-rounded";
import NextChapterIcon from "~icons/material-symbols/skip-next-rounded";
import PlayIcon from "~icons/material-symbols/play-arrow-rounded";
import PauseIcon from "~icons/material-symbols/pause-rounded";
import ReaderSettingsIcon from "~icons/material-symbols/tune-rounded";

import CloseIcon from "~icons/material-symbols/close-rounded";
import ClearIcon from "~icons/material-symbols/cancel-rounded";
import RetryIcon from "~icons/material-symbols/refresh-rounded";
import ExpandIcon from "~icons/material-symbols/unfold-more-rounded";
import CollapseIcon from "~icons/material-symbols/unfold-less-rounded";
import ChevronDownIcon from "~icons/material-symbols/keyboard-arrow-down-rounded";
import ChevronUpIcon from "~icons/material-symbols/keyboard-arrow-up-rounded";
import ChevronLeftIcon from "~icons/material-symbols/chevron-left-rounded";
import ChevronRightIcon from "~icons/material-symbols/chevron-right-rounded";
// `casino` has no rounded variant; the outlined glyph is the same family and
// is the only dice icon in the set.
import RandomIcon from "~icons/material-symbols/casino";
import SearchIcon from "~icons/material-symbols/search-rounded";
import DeleteIcon from "~icons/material-symbols/delete-rounded";
import CheckIcon from "~icons/material-symbols/check-rounded";
import VisibilityIcon from "~icons/material-symbols/visibility-rounded";

import ViewGridIcon from "~icons/material-symbols/grid-view-rounded";
import ViewListIcon from "~icons/material-symbols/view-list-rounded";
import ViewTableIcon from "~icons/material-symbols/table-rows-rounded";
import SortIcon from "~icons/material-symbols/sort-rounded";
import SortAscIcon from "~icons/material-symbols/arrow-upward-rounded";
import SortDescIcon from "~icons/material-symbols/arrow-downward-rounded";
import FilterIcon from "~icons/material-symbols/filter-list-rounded";
// `more-vert` / `more-horiz` have no rounded variant; `more` is the same
// vertical-overflow glyph with rounded corners.
import MoreIcon from "~icons/material-symbols/more-rounded";
import CopyIcon from "~icons/material-symbols/content-copy-rounded";
import ExternalLinkIcon from "~icons/material-symbols/open-in-new-rounded";

import StarIcon from "~icons/material-symbols/star-rounded";
import StarHalfIcon from "~icons/material-symbols/star-half-rounded";
import StarEmptyIcon from "~icons/material-symbols/star-outline-rounded";
import FavoriteOutlineIcon from "~icons/material-symbols/favorite-outline-rounded";
import StatusWarningIcon from "~icons/material-symbols/warning-rounded";
import StatusErrorIcon from "~icons/material-symbols/error-rounded";
import StatusInfoIcon from "~icons/material-symbols/info-rounded";
import StatusBlockedIcon from "~icons/material-symbols/do-not-disturb-on-rounded";
// `lock` has no rounded variant; a key is the closest rounded same-family
// glyph for "authentication required".
import StatusAuthIcon from "~icons/material-symbols/key-rounded";
import StatusChallengeIcon from "~icons/material-symbols/shield-rounded";
import AllSelectedIcon from "~icons/material-symbols/done-all-rounded";

export const iconRegistry = {
  // Navigation / app shell (AppShell.vue glyph table).
  browse: BrowseIcon,
  online: OnlineIcon,
  library: LibraryIcon,
  favorites: FavoritesIcon,
  downloads: DownloadsIcon,
  series: SeriesIcon,
  tags: TagsIcon,
  history: HistoryIcon,
  updates: UpdatesIcon,
  duplicates: DuplicatesIcon,
  recycle: RecycleIcon,
  integrity: IntegrityIcon,
  archive: ArchiveIcon,
  settings: SettingsIcon,
  logs: LogsIcon,
  menu: MenuIcon,
  notifications: NotificationsIcon,
  "global-controls": GlobalControlsIcon,
  logout: LogoutIcon,
  "theme-light": ThemeLightIcon,
  "theme-system": ThemeSystemIcon,
  "theme-dark": ThemeDarkIcon,
  language: LanguageIcon,

  // Reader chrome.
  back: BackIcon,
  forward: ForwardIcon,
  fullscreen: FullscreenIcon,
  "first-page": FirstPageIcon,
  "last-page": LastPageIcon,
  "next-chapter": NextChapterIcon,
  play: PlayIcon,
  pause: PauseIcon,
  "reader-settings": ReaderSettingsIcon,

  // Actions and disclosure.
  close: CloseIcon,
  clear: ClearIcon,
  retry: RetryIcon,
  expand: ExpandIcon,
  collapse: CollapseIcon,
  "chevron-down": ChevronDownIcon,
  "chevron-up": ChevronUpIcon,
  "chevron-left": ChevronLeftIcon,
  "chevron-right": ChevronRightIcon,
  random: RandomIcon,
  search: SearchIcon,
  delete: DeleteIcon,
  check: CheckIcon,
  visibility: VisibilityIcon,

  // Collection view switching, sorting and filtering.
  "view-grid": ViewGridIcon,
  "view-list": ViewListIcon,
  "view-table": ViewTableIcon,
  // Short aliases for the grid / list / table mode names used by page state.
  grid: ViewGridIcon,
  list: ViewListIcon,
  table: ViewTableIcon,
  sort: SortIcon,
  "sort-asc": SortAscIcon,
  "sort-desc": SortDescIcon,
  filter: FilterIcon,
  more: MoreIcon,
  copy: CopyIcon,
  "external-link": ExternalLinkIcon,

  // Ratings, favorites and status.
  star: StarIcon,
  "star-half": StarHalfIcon,
  "star-empty": StarEmptyIcon,
  favorite: FavoritesIcon,
  "favorite-outline": FavoriteOutlineIcon,
  "status-success": IntegrityIcon,
  "status-warning": StatusWarningIcon,
  "status-error": StatusErrorIcon,
  "status-info": StatusInfoIcon,
  "status-blocked": StatusBlockedIcon,
  "status-auth": StatusAuthIcon,
  "status-challenge": StatusChallengeIcon,
  "all-selected": AllSelectedIcon,
} as const;

export type IconName = keyof typeof iconRegistry;

/** Sorted semantic names; the `#/_kit` sample page renders every one. */
export const iconNames = Object.keys(iconRegistry).sort() as IconName[];
