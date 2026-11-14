"""Reading progress and history domain package.

``progress`` owns the local-library and online (ExHentai-only) reading
use-cases.  Routers inject repositories and lookups through the dataclasses
defined there, so the package never imports ``galleryvault.app.state`` or
``galleryvault.app.dependencies``.
"""

# Public surface for the router layer (T11.3): the reading use-cases live in
# ``reading.progress``, but callers import them from the package so that
# ``galleryvault.services.reading.*`` internals stay private.
from .progress import OnlineReadingDeps as OnlineReadingDeps
from .progress import ReadingDeps as ReadingDeps
from .progress import clear_all_progress as clear_all_progress
from .progress import delete_gallery_progress as delete_gallery_progress
from .progress import delete_history as delete_history
from .progress import get_gallery_progress as get_gallery_progress
from .progress import get_history as get_history
from .progress import get_online_progress as get_online_progress
from .progress import list_online_history as list_online_history
from .progress import save_online_progress as save_online_progress
from .progress import update_gallery_progress as update_gallery_progress
