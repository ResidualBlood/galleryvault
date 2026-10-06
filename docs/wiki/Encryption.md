# 静态加密

> **中文** · [English](Encryption-EN)

默认情况下敏感信息在数据库中是明文存储的。要启用静态加密，为 backend 服务设置 `ENCRYPTION_KEY` 环境变量（足够长的随机字符串）：

```yaml
    environment:
      ENCRYPTION_KEY: 请改成足够长的随机字符串
```

启用后（下次启动生效）：

- ExHentai cookies、Telegram bot token、`auth_secret` 与管理员密码哈希以 **AES-256-GCM** 加密存储（标识为 `enc:v1:...`）。
- 启动时已有明文自动迁移为密文，无需停机。
- 未设置 `ENCRYPTION_KEY` 时，敏感字段以明文保存，系统正常工作。

**安全提示**：密钥必须独立于数据库及数据库备份单独保存（例如存入密码管理器）。**密钥一旦丢失，已加密的 cookies、token、密码哈希与 `auth_secret` 将无法解密。**

## AUTH_SECRET 与 ENCRYPTION_KEY 协作机制

系统使用两个用途独立的密钥：

| 密钥 | 核心职责 | 保存位置与行为 | 环境变量未配置时的表现 |
| :--- | :--- | :--- | :--- |
| **AUTH_SECRET** | 用于 Web 会话 Cookie（`galleryvault_session`）的 HMAC-SHA256 签名校验。 | 写入数据库 `app_config` 表中的 `runtime_auth` 字段（配置加密时存为密文）。 | 后端首次启动自动生成 32 字节随机密钥写入数据库；重启时自动复用，用户登录态不失效。若配置了环境变量则优先采用。 |
| **ENCRYPTION_KEY** | 用于数据库中敏感字段的 AES-256-GCM 静态存储加密。 | 由环境变量注入，严禁写入数据库。 | 不启用静态加密，字段以明文落库，认证与业务功能正常运作。配置后落库数据自动转为 `enc:v1:...` 密文。 |

## 密钥丢失的恢复

`ENCRYPTION_KEY` 丢失后，旧密文无法使用新密钥解密。

### 操作影响与重置风险

- **管理员密码重置**：重置 `runtime_auth` 会使管理员密码回到默认密码 `p1a2s3s4`，所有既有设备登录会话即时作废失效。
- **配置项需重新填写**：ExHentai cookies 与 Telegram bot token 密文将被清理，启动后必须在设置中重新填写。
- **备份还原前提**：若持有**加密前**的数据库备份，可直接还原备份（参见 [备份与恢复](Backup#恢复)），再配置新密钥，无需手动执行下列清除命令。

### 恢复步骤

```bash
# 1) 停止 backend 容器
docker stop galleryvault-backend

# 2) 重置认证凭据：清除 runtime_auth，密码回到默认 p1a2s3s4，auth_secret 下次启动重新生成
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "DELETE FROM app_config WHERE key='runtime_auth';"

# 3) 清除无法解密的旧密文 cookies 与 bot token
docker exec galleryvault-db psql -U galleryvault -d galleryvault \
  -c "UPDATE app_config SET value = value - 'exhentai_cookies' - 'telegram_bot_token' WHERE key='user_settings';"

# 4) 在 Compose 中配置新的 ENCRYPTION_KEY 并启动 backend
docker start galleryvault-backend
```

容器启动后，请立即使用默认密码 `p1a2s3s4` 登录系统修改密码，并在「系统设置」中重新填写 ExHentai cookies 与 Telegram bot token。
