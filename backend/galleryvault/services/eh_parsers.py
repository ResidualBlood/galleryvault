"""Pure parsing helpers for the ExHentai client (no HTTP transport).

The implementation now lives in :mod:`galleryvault.services.eh.parsers`, split
by domain (errors / gallery / search / favorites / archive / showpage).  This
module keeps the historical import path and re-exports every symbol unchanged;
``galleryvault.services.eh_client`` still imports from here.
"""

from __future__ import annotations

from .eh import parsers as _parsers
from .eh.parsers.archive import *
from .eh.parsers.errors import *
from .eh.parsers.favorites import *
from .eh.parsers.gallery import *
from .eh.parsers.search import *
from .eh.parsers.showpage import *

__all__ = _parsers.__all__
