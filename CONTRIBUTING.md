# Contributing to GalleryVault

Thanks for your interest! This project is made of three repositories:

| Repository | Purpose |
|------------|---------|
| [`galleryvault`](https://github.com/ResidualBlood/galleryvault) | Deployment (`docker-compose.yml`), docs (wiki/README), scripts |
| [`galleryvault-backend`](https://github.com/ResidualBlood/galleryvault-backend) | FastAPI + PostgreSQL API, scanners, services |
| [`galleryvault-frontend`](https://github.com/ResidualBlood/galleryvault-frontend) | Vanilla-JS SPA (no build step, no dependencies) |

Report bugs, request features, or ask questions in the **galleryvault** repository
(issues are aggregated there); code PRs go to `galleryvault-backend` or
`galleryvault-frontend`.

## Code of Conduct

Please note that this project has a [Code of Conduct](CODE_OF_CONDUCT.md).
By participating you agree to abide by its terms.

## Getting started

1. Fork the relevant repository and clone it.
2. Create a feature branch: `git switch -c feature/my-change`.
3. Make your change following the conventions below.
4. Run the checks and make sure CI passes.
5. Open a Pull Request against `main` using the PR template.

## Conventions

- **Python (backend)**: format/line length follows `pyproject.toml` (`ruff`,
  line length 100). Run `ruff check .` before committing.
- **JavaScript (frontend)**: keep the vanilla-JS, no-build, no-CDN rule — new
  code must not add build steps or third-party runtimes. `node --check
  assets/app.js` must pass.
- **Migration**: schema changes go through Alembic (`alembic revision
  --autogenerate`), then `alembic upgrade head`. Never hand-edit committed
  migrations.
- **Backward compatibility**: existing settings and stored data must keep
  working; prefer additive changes and auto-migration over breaking ones.
- **Security**: never log cookies, tokens or secrets; sensitive values are
  stored via `galleryvault.secrets` (encrypted when `ENCRYPTION_KEY` is set).
- **Tests**: add/extend tests under `tests/`. The CI enforces a coverage gate
  (`--cov-fail-under=45`).
- **Docs**: user-facing changes should be reflected in the
  [wiki](https://github.com/ResidualBlood/galleryvault/wiki) or `docs/` notes.

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
pip install -e ".[dev]"
DATABASE_URL=postgresql+asyncpg://galleryvault:galleryvault@localhost:5432/galleryvault alembic upgrade head
pytest -q --cov=galleryvault --cov-report=term-missing --cov-fail-under=45
```

The frontend has no build step; validate with `node --check assets/app.js`.

## Releasing

Maintainers tag `vX.Y.Z` on the backend and frontend repositories; CI builds the
matching Docker Hub image tags and a GitHub Release is created from
`CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/)).
