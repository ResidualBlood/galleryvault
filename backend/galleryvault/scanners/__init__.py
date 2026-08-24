from .archive import CbrRarScanner, CbzZipScanner
from .base import GalleryMeta, GalleryScanner, PageInfo, ScannerRegistry
from .ehviewer import (
    BareImageDirScanner,
    EhviewerDirScanner,
    SpiderInfo,
    SpiderPageEntry,
    parse_spider_info,
)

registry = ScannerRegistry()
registry.register(EhviewerDirScanner())
registry.register(CbzZipScanner())
registry.register(CbrRarScanner())
registry.register(BareImageDirScanner())

__all__ = [
    "GalleryMeta",
    "GalleryScanner",
    "PageInfo",
    "ScannerRegistry",
    "SpiderInfo",
    "SpiderPageEntry",
    "parse_spider_info",
    "registry",
]
