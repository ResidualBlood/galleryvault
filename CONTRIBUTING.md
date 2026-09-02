# Contributing to GalleryVault

Thanks for your interest! This project is organized as a monorepo containing:

| Directory | Purpose |
|-----------|---------|
| `backend/` | FastAPI + PostgreSQL API, scanners, services |
| `frontend/` | Vanilla-JS SPA (no build step, no dependencies) |
| `docs/wiki/` | Canonical wiki documentation (bilingual) |
| `docs-site/` | VitePress documentation website |
| `/` | Deployment (`docker-compose.yml`), CI workflows, scripts |

Report bugs, request features, or submit pull requests directly in this repository ([`galleryvault`](https://github.com/ResidualBlood/galleryvault)).

## Code of Conduct

Please note that this project has a [Code of Conduct](CODE_OF_CONDUCT.md).
By participating you agree to abide by its terms.

## Getting started

1. Fork this repository and clone it.
2. Create a feature branch from `dev`: `git switch -c feature/my-change origin/dev`.
3. Make your change following the conventions below.
4. Run the checks and make sure CI passes.
5. Open a Pull Request against `dev` using the PR template.

Optional: install [pre-commit](https://pre-commit.com) (`pip install pre-commit && pre-commit install`) to run the formatting/secret hooks locally before committing.

## Conventions

- **Python (backend)**: format/line length follows `backend/pyproject.toml` (`ruff`, line length 100). Run `ruff check .` inside `backend/` before committing.
- **JavaScript (frontend)**: keep the vanilla-JS, no-build, no-CDN rule — new code must not add build steps or third-party runtimes. `node --check assets/app.js` must pass.
- **Migration**: schema changes go through Alembic (`alembic revision --autogenerate`), then `alembic upgrade head`. Never hand-edit committed migrations.
- **Backward compatibility**: existing settings and stored data must keep working; prefer additive changes and auto-migration over breaking ones.
- **Security**: never log cookies, tokens or secrets; sensitive values are stored via `galleryvault.secrets` (encrypted when `ENCRYPTION_KEY` is set).
- **Tests**: add/extend tests under `backend/tests/`. The CI enforces a coverage gate (`--cov-fail-under=45`).
- **Docs**: user-facing changes should be reflected in `docs/wiki/` or `backend/docs/`.

## Commit messages

Concise summary line, optionally followed by a blank line and a short body.
Reference the issue when applicable, e.g.:

```
downloads: resume only the missing pages on retry

Fixes #42
```

## Testing

Backend tests require PostgreSQL (the CI runs one via a service container):

```bash
cd backend
pip install -e ".[dev]"
DATABASE_URL=postgresql+asyncpg://galleryvault:galleryvault@localhost:5432/galleryvault alembic upgrade head
pytest -q --cov=galleryvault --cov-report=term-missing --cov-fail-under=45
```

The frontend has no build step; validate with:

```bash
cd frontend
for f in assets/*.js assets/locales/*.js assets/views/*.js; do node --check "$f"; done
```

## Releasing

Maintainers tag `vX.Y.Z` on the `galleryvault` repository; CI builds both Docker Hub images (`galleryvault-backend` and `galleryvault-frontend`) and a GitHub Release is created from `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/)).
