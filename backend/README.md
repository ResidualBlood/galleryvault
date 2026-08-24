# GalleryVault Backend

FastAPI + PostgreSQL JSON API for GalleryVault. The SPA lives in the
[`galleryvault-frontend`](../frontend) repository.

- API: `http://<host>:8001/api/*`
- Health: `http://<host>:8001/healthz`
- Login/Logout: `POST /login`, `POST /logout` (form/cookie based)

Run the full stack (frontend :8000, backend :8001, PostgreSQL) with the
`docker-compose.yml` in this directory.

See `docs/API.md` for the endpoint list and `docs/DEVELOPMENT.md` for
architecture notes.