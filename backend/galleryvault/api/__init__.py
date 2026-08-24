"""GalleryVault backend HTTP API.

This package is the authoritative reference for the backend contract. The
backend returns only JSON (or a binary stream such as an image); the
single-page frontend lives in the separate ``galleryvault-frontend``
repository and is served by its own nginx container.

Route handlers are defined in :mod:`galleryvault.app.main` and registered on
the FastAPI ``app`` instance. This module re-exports the handler callables and
documents every endpoint so the contract is easy to locate and reuse.
"""

from galleryvault.app.main import (  # noqa: F401
    auth_session,
    cancel_download,
    check_favorites,
    clear_history,
    create_download,
    favorite_categories,
    gallery_detail,
    gallery_list,
    gallery_page,
    gallery_progress,
    gallery_random,
    history,
    list_downloads,
    login,
    logout,
    save_gallery_progress,
    scan_status,
    settings_get,
    settings_save,
    settings_test_exhentai,
    sync_favorite_categories,
    sync_gallery_tags,
    tag_search,
    tag_sync_status,
    trigger_scan,
    update_favorite_category,
)

#: Machine-readable description of every public endpoint. Consumed by the docs
#: generator and useful as a single source of truth for the frontend.
API_ROUTES = [
    {"method": "GET", "path": "/healthz", "auth": False,
     "summary": "Liveness probe."},
    {"method": "GET", "path": "/api/auth/session", "auth": True,
     "summary": "Returns the authenticated session state."},
    {"method": "POST", "path": "/login", "auth": False,
     "summary": "Authenticate with the instance password; sets the session cookie."},
    {"method": "POST", "path": "/logout", "auth": False,
     "summary": "Clear the session cookie."},

    {"method": "GET", "path": "/api/settings", "auth": True,
     "summary": "Current effective settings (public subset)."},
    {"method": "POST", "path": "/api/settings", "auth": True,
     "summary": "Persist settings (library roots, proxies, favorites, ...)."},
    {"method": "POST", "path": "/api/settings/exhentai/test", "auth": True,
     "summary": "Validate the configured ExHentai cookies."},

    {"method": "POST", "path": "/api/downloads", "auth": True,
     "summary": "Enqueue a gallery download."},
    {"method": "GET", "path": "/api/downloads", "auth": True,
     "summary": "Paginated download task list."},
    {"method": "POST", "path": "/api/downloads/{task_id}/cancel", "auth": True,
     "summary": "Cancel a pending/active download."},

    {"method": "GET", "path": "/api/favorites/categories", "auth": True,
     "summary": "List the ten ExHentai favorite folders."},
    {"method": "POST", "path": "/api/favorites/categories", "auth": True,
     "summary": "Enable/disable or change the mode of a favorite folder."},
    {"method": "POST", "path": "/api/favorites/sync-categories", "auth": True,
     "summary": "Refresh folder names from ExHentai."},
    {"method": "POST", "path": "/api/favorites/{favcat}/check", "auth": True,
     "summary": "Scan a favorite folder and enqueue missing galleries."},

    {"method": "GET", "path": "/api/galleries", "auth": True,
     "summary": "Search/browse the local library."},
    {"method": "GET", "path": "/api/galleries/random", "auth": True,
     "summary": "Return a random gallery id."},
    {"method": "GET", "path": "/api/galleries/{identifier}", "auth": True,
     "summary": "Gallery metadata, pages and tags."},
    {"method": "GET", "path": "/api/galleries/{identifier}/progress", "auth": True,
     "summary": "Reading progress for a gallery."},
    {"method": "PUT", "path": "/api/galleries/{identifier}/progress", "auth": True,
     "summary": "Record reading progress."},
    {"method": "POST", "path": "/api/galleries/{identifier}/sync-tags", "auth": True,
     "summary": "Sync tags from ExHentai for one gallery."},
    {"method": "GET", "path": "/api/galleries/{identifier}/pages/{page_index}",
     "auth": True, "summary": "Stream one page image."},

    {"method": "GET", "path": "/api/history", "auth": True,
     "summary": "Reading history."},
    {"method": "DELETE", "path": "/api/history", "auth": True,
     "summary": "Clear reading history."},

    {"method": "GET", "path": "/api/tags/search", "auth": True,
     "summary": "Search local tags (optional ?namespace= filter); includes translations."},

    {"method": "GET", "path": "/api/scan", "auth": True,
     "summary": "Current library scan status."},
    {"method": "POST", "path": "/api/scan", "auth": True,
     "summary": "Trigger a library scan."},
    {"method": "GET", "path": "/api/tag-sync/status", "auth": True,
     "summary": "Background tag-sync worker status."},
]
