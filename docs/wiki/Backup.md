# 备份与恢复

数据库是唯一必须备份的状态（画廊索引、设置、历史；缩略图与画廊文件本身可重建）。

## 备份

仓库提供 `scripts/backup.sh`，在 `docker-compose.yml` 所在目录运行：

```bash
./scripts/backup.sh        # 生成 backups/galleryvault_<时间戳>.dump，保留最近 14 份
```

推荐通过 cron 每日执行，例如：

```
0 3 * * * cd /path/to/galleryvault && ./scripts/backup.sh
```

## 恢复

```bash
docker compose exec -T db pg_restore -U galleryvault -d galleryvault -c --if-exists \
  < backups/galleryvault_<时间戳>.dump
```

> 恢复会覆盖当前数据库内容。若备份早于启用加密，恢复后按 [静态加密](Encryption) 重新设置 `ENCRYPTION_KEY` 即可。

## 备份中的密钥

启用 [静态加密](Encryption) 后，数据库备份里的 cookie / token 是密文。**备份文件不包含密钥**——请把 `ENCRYPTION_KEY` 单独存放在密码管理器中，与备份分开保管。
