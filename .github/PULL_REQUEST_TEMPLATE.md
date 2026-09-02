## What does this PR do?

<!-- A short summary of the change and why it is needed. -->

## Checklist

- [ ] Ran the checks (backend: `ruff check .` + `pytest`; frontend: `for f in assets/*.js assets/locales/*.js assets/views/*.js; do node --check "$f"; done`)
- [ ] Schema changes go through an Alembic migration (`alembic revision --autogenerate`)
- [ ] Backward compatible; existing settings/data keep working
- [ ] No secrets/cookies/tokens logged or added to the repo
- [ ] User-facing changes reflected in the [wiki](https://github.com/ResidualBlood/galleryvault/wiki) or `docs/`
- [ ] Added/extended tests where applicable

## Related issues

<!-- Fixes #123 -->
