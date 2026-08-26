"""GalleryVault backend HTTP API.

Route handlers live in :mod:`galleryvault.app.routers` (split by domain:
``core``, ``tasks``, ``settings``, ``downloads``, ``favorites``, ``galleries``,
``tags``) and are registered on the FastAPI app in :mod:`galleryvault.app.main`.
The main module keeps the shared task state, background workers, helpers,
middleware, the lifespan, and the auth routes.

See ``docs/API.md`` for the authoritative endpoint reference, and
``docs/DEVELOPMENT.md`` for the project layout.
"""
