# 备份与恢复

数据库是唯一必须备份的状态（画廊索引、设置、历史；缩略图与画廊文件本身可重建）。

## 备份

`scripts/backup.sh` 在线 `pg_dump`，不停服务。在 `docker-compose.yml` 所在目录运行：

```bash
./scripts/backup.sh        # 生成 backups/galleryvault_<时间戳>.dump，保留最近 14 份
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

## 离线全量修复与元数据清洗工具

当外部导入、多工具反复迁移或早期历史版本导致画廊出现脏数据（如文件名超长、前导多重 GID 污染或元数据损坏）时，可在离线维护状态下使用系统提供的运维修复脚本。

### 1. 冷库与本地目录全量修复脚本 (`repair_cold_archives.py`)

脚本位于 `backend/galleryvault/scripts/repair_cold_archives.py`，用于对本地目录及冷库 CBZ 归档进行深度健康检查、去污与元数据重构。

- **核心功能**：
  - **支持 `--dry-run` 预览**：在安全模拟模式下仅打印扫描出的脏文件、拟修复的新文件名与元数据变更计划，不改动磁盘文件，便于运维人员事前核对。
  - **剥离前导重复 GID**：自动检测并剥离如 `[12345] 12345-标题`、`12345-12345-标题` 等历史迁移导致的重复 GID 脏前缀，恢复标准 `gid-标题` 格式。
  - **双重 GID 污染清洗与重命名**：同时清洗本地散图文件夹与冷库 CBZ 文件，清除文件名与内部索引内的畸形 GID 叠加。
  - **分片批量 GData 洗白**：自动收集清洗后的有效 GID，分片批量回查云端官方 GData API，拉取权威标题、标签与分类重构 `.galleryvault.json` Sidecar 索引，彻底洗净脏数据。

- **使用方法**：
  ```bash
  # 1. 演练模式（Dry Run）：仅检查并输出清洗预览，不实际修改文件
  python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive --dry-run

  # 2. 正式执行：批量剥离冗余 GID、重构索引并清洗冷库文件
  python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive
  ```

### 2. CBZ 超长文件名对齐工具 (`repair_cbz_filenames.py`)

脚本位于 `scripts/repair_cbz_filenames.py`，专门解决历史旧归档在 Linux ext4 文件系统上因多字节字符超长导致的报错。

- **核心功能**：
  - **243 字节上限对齐**：遍历目标归档目录，对所有历史旧 CBZ 文件自动应用 Linux ext4 243 字节文件名截断规范（为 `.cbz.partial` 预留 12 字节，保证总文件名 ≤ 255 字节）。
  - **彻底消灭 Errno 36**：消除中日韩多字节特殊符号引发的 `[Errno 36] File name too long`，确保归档包在移动、备份或网盘同步时保持高度兼容。

- **使用方法**：
  ```bash
  # 扫描并自动规范化对齐旧 CBZ 归档文件名
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```
