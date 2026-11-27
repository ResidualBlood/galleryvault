## What does this PR do?

<!-- A short summary of the change and why it is needed. -->

## Checklist

- [ ] Ran the checks (backend: `ruff check .` + `pytest`; frontend: `npm --prefix frontend ci && npm --prefix frontend run typecheck && npm --prefix frontend run lint && npm --prefix frontend run test:unit && npm --prefix frontend run build`)
- [ ] Schema changes go through an Alembic migration (`alembic revision --autogenerate`)
- [ ] Backward compatible; existing settings/data keep working
- [ ] No secrets/cookies/tokens logged or added to the repo
- [ ] User-facing changes reflected in the [wiki](https://github.com/ResidualBlood/galleryvault/wiki) or `docs/`
- [ ] Added/extended tests where applicable

## Related issues

<!-- Fixes #123 -->
