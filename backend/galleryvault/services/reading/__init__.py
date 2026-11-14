"""Reading progress and history domain package.

``progress`` owns the local-library and online (ExHentai-only) reading
use-cases.  Routers inject repositories and lookups through the dataclasses
defined there, so the package never imports ``galleryvault.app.state`` or
``galleryvault.app.dependencies``.
"""
