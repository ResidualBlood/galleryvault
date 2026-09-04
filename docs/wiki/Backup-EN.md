# Backup & Restore

The database is the only state that must be backed up (gallery index, settings,
history; thumbnails and the gallery files themselves are rebuildable).

## Backup

`scripts/backup.sh` runs `pg_dump` online; do not stop services. Run it from the directory containing `docker-compose.yml`:

```bash
./scripts/backup.sh        # writes backups/galleryvault_<timestamp>.dump, keeps the 14 most recent
```

Recommended via cron, for example:

```
0 3 * * * cd /path/to/galleryvault && ./scripts/backup.sh
```

## Restore

There is no `restore.sh`; restore with the commands on this page. Stop backend before restore, then `pg_restore -c --if-exists`:

```bash
docker compose exec -T db pg_restore -U galleryvault -d galleryvault -c --if-exists \
  < backups/galleryvault_<timestamp>.dump
```

> Restoring overwrites the current database. If the backup predates encryption,
> just set `ENCRYPTION_KEY` again afterwards — see
> [Encryption](Encryption-EN).

## The key in backups

With [encryption at rest](Encryption-EN) enabled, cookies / tokens in the
database backup are ciphertext. **The backup does not contain the key** — keep
`ENCRYPTION_KEY` in a password manager, separate from the backup. If the key is
lost, see [Encryption at Rest → Recovering from a lost key](Encryption-EN#recovering-from-a-lost-key).
