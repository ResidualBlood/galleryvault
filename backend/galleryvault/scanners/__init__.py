from .archive import CbrRarScanner, CbzZipScanner
from .base import GalleryMeta, GalleryScanner, PageInfo, ScannerRegistry
from .ehviewer import (
    BareImageDirScanner,
    EhviewerDirScanner,
    JhentaiDirScanner,
    SpiderInfo,
    SpiderPageEntry,
    parse_spider_info,
)
from .pdf import PdfScanner
from .sevenzip import SevenZipScanner

registry = ScannerRegistry()
registry.register(EhviewerDirScanner())
registry.register(JhentaiDirScanner())
registry.register(CbzZipScanner())
registry.register(CbrRarScanner())
registry.register(SevenZipScanner())
registry.register(PdfScanner())
registry.register(BareImageDirScanner())

__all__ = [
    "GalleryMeta",
    "GalleryScanner",
    "PageInfo",
    "PdfScanner",
    "ScannerRegistry",
    "SevenZipScanner",
    "SpiderInfo",
    "SpiderPageEntry",
    "parse_spider_info",
    "registry",
]
