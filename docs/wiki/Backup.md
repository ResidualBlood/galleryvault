# 备份与恢复

数据库是唯一必须备份的状态（画廊索引、设置、历史；缩略图与画廊文件本身可重建）。

## 备份

完整仓库里的 `scripts/backup.sh` 做在线 `pg_dump`（不停服务）。**只 curl 了 `docker-compose.yml` 的目录没有这个脚本**，请用下面的 `pg_dump`，或先克隆仓库。

```bash
# 有完整仓库时：
./scripts/backup.sh        # 生成 backups/galleryvault_<时间戳>.dump，保留最近 14 份

# 等价：
docker compose exec -T db pg_dump -U galleryvault -Fc galleryvault > backups/galleryvault_$(date +%Y%m%d).dump
```

推荐通过 cron 每日执行，例如：

```
0 3 * * * cd /path/to/galleryvault && ./scripts/backup.sh
```

## 恢复

仓库无 `restore.sh`，恢复用页面上的命令。恢复前建议先停 backend，再 `pg_restore -c --if-exists`：

```bash
docker compose exec -T db pg_restore -U galleryvault -d galleryvault -c --if-exists \
  < backups/galleryvault_<时间戳>.dump
```

> 恢复会覆盖当前数据库内容。若备份早于启用加密，恢复后按 [静态加密](Encryption) 重新设置 `ENCRYPTION_KEY` 即可。

## 备份中的密钥

启用 [静态加密](Encryption) 后，数据库备份里的 cookie / token 是密文。**备份文件不包含密钥**——请把 `ENCRYPTION_KEY` 单独存放在密码管理器中，与备份分开保管。若密钥遗失，凭据恢复流程见 [静态加密 → 密钥丢失的恢复](Encryption#密钥丢失的恢复)。

---

## 冷存储归档多根目录与英文命名规范

GalleryVault 支持通过分层冷存储降低热盘占用。冷存储数据卷中的归档文件与元数据同样属于重要资产，建议纳入定期备份范畴。

### 1. 多根目录配置与容量负载均衡 (`archive_roots`)
- 冷存储多盘挂载、`archive_roots` 路径配置、基于 `statvfs` 的动态容量均衡规则以及安全清理操作，详见 [部署指南 → 冷热分层存储、多盘挂载与归档规则](Deployment#2-冷热分层存储多盘挂载与归档规则)。
- 执行安全反向清理（`POST /api/system/purge-archived-sources`）时，系统会自动跳过处于活跃下载状态的任务，确认冷存储完整后清理散图源目录。

### 2. 英文固定命名规范 (`gid-gallery.title.cbz`)
- 冷归档统一采用官方英文/罗马音标题命名，以保障在跨操作系统及文件共享协议（SMB / NFS / WebDAV / rsync）传输时的兼容性。
- 归档文件名的 243 字节上限截断、12 字节临时后缀缓冲与 247 字节目录名限制表，详见 [兼容性与格式规范 → 格式降级与容错处理](Compatibility#格式降级与容错处理)。

---

## 离线全量修复与元数据清洗工具

当外部导入、历史迁移或非规范工具导致归档存在前导 GID 污染或超长文件名时，可在离线维护状态下使用系统提供的脚本工具。完整参数列表与命令行范例详见 [部署指南 → 运维工具与离线修复脚本速查](Deployment#运维工具与离线修复脚本速查)。

### 1. 冷库与本地目录全量修复脚本 (`repair_cold_archives.py`)
- **适用场景**：批量清理如 `[12345] 12345-标题` 的重复前导 GID 脏前缀，并调用云端 GData 接口重新生成 `.galleryvault.json` 索引。
- **操作安全**：支持 `--dry-run` 预览修改项；推荐在后端 Docker 容器内执行。具体命令参见 [部署指南 → 冷库与本地目录全量修复](Deployment#1-冷库与本地目录全量修复-repair_cold_archivespy)。

### 2. CBZ 超长文件名对齐工具 (`repair_cbz_filenames.py`)
- **适用场景**：扫描目标目录，将历史超长 CBZ 文件名按 243 字节上限对齐截断，解决底层文件系统报错。
- **操作要求**：该脚本位于仓库根目录 `scripts/`，未打包进 Docker 镜像，须在宿主机直接执行。具体命令参见 [部署指南 → CBZ 超长文件名 243 字节对齐](Deployment#2-cbz-超长文件名-243-字节对齐-repair_cbz_filenamespy)。
