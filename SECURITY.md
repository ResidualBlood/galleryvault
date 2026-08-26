# Security Policy

GalleryVault stores sensitive data — ExHentai cookies, a Telegram bot token,
session tokens and (when enabled) encrypted credentials. Please report security
issues responsibly.

## Supported versions

Only the latest tagged release on `main` is supported. The `latest` Docker Hub
images track `main`.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

- Prefer a **private disclosure**: open a [Security advisory](https://github.com/ResidualBlood/galleryvault/security/advisories/new)
  on the main repository.
- Or email the maintainers privately (address available in the advisory page /
  maintainer profile).

When reporting, please include:

- Which repository and version/commit is affected
- A description of the vulnerability and its impact
- Steps to reproduce (if any)
- Any suggested fix, if you have one

We aim to acknowledge reports within 72 hours and to respond with a status
update within 7 days.

## Security-relevant areas

- Authentication & session handling (`POST /login`, cookies, `auth_secret`)
- At-rest encryption (`ENCRYPTION_KEY`, `galleryvault/secrets.py`)
- Rate limiting and the nginx proxy config
- Anything that handles or persists ExHentai cookies / Telegram tokens

## Good practices for self-hosting

See the [wiki](https://github.com/ResidualBlood/galleryvault/wiki) for the
public-deployment checklist: change the default password, enable TLS
(`AUTH_COOKIE_SECURE=true`), keep the backend bound to `127.0.0.1`, set a strong
PostgreSQL password, and store `ENCRYPTION_KEY` outside the database backup.
