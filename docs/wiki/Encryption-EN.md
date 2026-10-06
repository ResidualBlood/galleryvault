# Encryption at Rest

> [中文](Encryption) · **English**

By default, sensitive values are stored in plaintext in the database. To enable encryption at rest, configure the `ENCRYPTION_KEY` environment variable on the backend service (a long random string):

```yaml
    environment:
      ENCRYPTION_KEY: change-me-to-a-long-random-string
```

Once enabled (takes effect on the next start):

- ExHentai cookies, Telegram bot token, `auth_secret`, and administrator password hash are stored encrypted using **AES-256-GCM** (marked with `enc:v1:...`).
- Existing plaintext values migrate automatically at startup without downtime.
- When `ENCRYPTION_KEY` is unset, sensitive fields remain in plaintext and features continue working.

**Security Notice**: Keep the key separate from the database and database backups (such as in a password manager). **If the key is lost, encrypted cookies, tokens, password hashes, and `auth_secret` cannot be decrypted.**

## Cooperation between AUTH_SECRET and ENCRYPTION_KEY

The system uses two keys with distinct responsibilities:

| Key | Primary Responsibility | Storage Location & Behavior | Behavior When Unset in Environment |
| :--- | :--- | :--- | :--- |
| **AUTH_SECRET** | Signs web session cookies (`galleryvault_session`) using HMAC-SHA256. | Stored in the `app_config` table under `runtime_auth` (encrypted as ciphertext when encryption is enabled). | The backend automatically generates a secure 32-byte random key on first launch and stores it in the database; it is reused across restarts so user sessions survive container restarts. When explicitly configured in the environment, the environment variable takes precedence. |
| **ENCRYPTION_KEY** | Serves as the master key for database at-rest protection (AES-256-GCM). | Injected via environment variables; never written to the database. | Encryption at rest is disabled, values are stored in plaintext, and authentication and features work normally. When set, persisted target values automatically convert to `enc:v1:...` ciphertext. |

## Recovering from a lost key

Once `ENCRYPTION_KEY` is lost, existing ciphertext cannot be decrypted with a new key.

### Impact and Reset Risks

- **Administrator password reset**: Resetting `runtime_auth` restores the administrator password to the default `p1a2s3s4`, immediately invalidating active web sessions on all devices.
- **Settings re-entry**: Encrypted cookies and Telegram bot tokens are cleared and must be re-entered in Settings after startup.
- **Pre-encryption backup restore**: If you hold a **pre-encryption** database backup, restore it directly (see [Backup & Restore](Backup-EN#restore)) and configure a new key, without needing manual clearing commands.

### Recovery Procedure

```bash
# 1) Stop the backend container
docker stop galleryvault-backend

# 2) Reset authentication credentials: remove runtime_auth, revert password to default p1a2s3s4, regenerate auth_secret on startup
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "DELETE FROM app_config WHERE key='runtime_auth';"

# 3) Clear unrecoverable encrypted cookies and bot token
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "UPDATE app_config SET value = value - 'exhentai_cookies' - 'telegram_bot_token' WHERE key='user_settings';"

# 4) Configure a new ENCRYPTION_KEY in Compose and start the backend
docker start galleryvault-backend
```

After startup, log in with the default password `p1a2s3s4`, change the password immediately, and re-enter your ExHentai cookies and Telegram bot token under Settings.
