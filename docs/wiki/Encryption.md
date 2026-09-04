# 静态加密

默认情况下敏感信息在数据库中是**明文**存储的——任何拿到数据库（或备份）的人都能读到。要启用静态加密，为 backend 设置 `ENCRYPTION_KEY` 环境变量（一个足够长的随机串）：

```yaml
    environment:
      ENCRYPTION_KEY: 请改成足够长的随机字符串
```

启用后（下次启动即生效）：

- ExHentai cookies、Telegram bot token、`auth_secret`、密码哈希以 **AES-256-GCM** 加密存储（`enc:v1:...`）；
- 已有明文值在启动时**自动迁移**为密文，无需停机；
- 未设置 `ENCRYPTION_KEY` 时一切照旧（明文存储，行为不变）。

**重要**：密钥必须独立于数据库妥善保管（例如密码管理器），与数据库备份分开放置——**密钥丢失后，已加密的 cookie / token / 密码哈希将无法解密**。

## 密钥丢失的恢复

`ENCRYPTION_KEY` 丢失后，已加密的值（旧 `enc:v1:` 密文）用新密钥无法解密。cookies / bot token 可以在设置页重新填写覆盖，但 `auth_secret` 与密码哈希没有 API 可重置，必须清掉旧密文让系统重新生成：

```bash
# 1) 停止 backend
docker stop galleryvault-backend
# 2) 重置认证凭据：auth_secret 重新生成、密码回到默认 p1a2s3s4
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "DELETE FROM app_config WHERE key='runtime_auth';"
# 3) 清掉旧密文的 cookies / bot token（之后在设置页重新填写）
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "UPDATE app_config SET value = value - 'exhentai_cookies' - 'telegram_bot_token' WHERE key='user_settings';"
# 4) 换上新的 ENCRYPTION_KEY 并启动
docker start galleryvault-backend
```

启动后使用默认密码 `p1a2s3s4` 登录，然后立即在设置中改密码并重新填写 ExHentai cookies / Telegram token。

> 只要还持有**加密前**的数据库备份，就能直接恢复（参见 [备份与恢复](Backup#恢复) 还原备份后按上面的流程重新设置密钥），无需清库。
