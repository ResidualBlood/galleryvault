# Encryption at Rest

By default the sensitive values are stored **in plaintext** in the database —
anyone who gets the database (or a backup) can read them. To enable encryption
at rest, set the `ENCRYPTION_KEY` environment variable on the backend service
(a long random string):

```yaml
    environment:
      ENCRYPTION_KEY: change-me-to-a-long-random-string
```

Once enabled (takes effect on the next start):

- ExHentai cookies, the Telegram bot token, `auth_secret` and the password hash
  are stored encrypted (**AES-256-GCM**, `enc:v1:...`);
- existing plaintext values are **migrated automatically** at startup — no
  downtime;
- without `ENCRYPTION_KEY` everything keeps working unchanged (plaintext
  storage).

**Important**: keep the key separate from the database backup and store it
safely (e.g. a password manager) — **if the key is lost, the encrypted cookies /
token / password hash cannot be decrypted**.

## Recovering from a lost key

Once `ENCRYPTION_KEY` is lost, the old `enc:v1:` values cannot be decrypted
with a new key. Cookies / the bot token can be re-entered in Settings, but
`auth_secret` and the password hash have no API to reset — clear the old
ciphertext so the system regenerates them:

```bash
# 1) stop the backend
docker stop galleryvault-backend
# 2) reset auth credentials: auth_secret is regenerated, password returns to the default p1a2s3s4
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "DELETE FROM app_config WHERE key='runtime_auth';"
# 3) clear the old encrypted cookies / bot token (re-enter them in Settings later)
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "UPDATE app_config SET value = value - 'exhentai_cookies' - 'telegram_bot_token' WHERE key='user_settings';"
# 4) set a new ENCRYPTION_KEY and start
docker start galleryvault-backend
```

Log in with the default password `p1a2s3s4`, then change it and re-enter your
ExHentai cookies / Telegram token in Settings.

> If you still hold a **pre-encryption** database backup, restore it and then
> follow the steps above to set a fresh key — no clearing needed.
