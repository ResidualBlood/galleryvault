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

GalleryVault 支持通过分层冷存储降低热盘占用，并在备份与跨平台迁移时保证极致兼容性：

### 1. 多根目录配置与容量负载均衡 (`archive_roots`)
- **多行路径配置**：在「系统设置 → 资料库」的冷归档目录中，支持填写多个容器内挂载路径（每行一条，例如 `/archive1` 与 `/archive2`），对应后端配置项 `archive_roots`。
- **动态容量负载均衡**：当归档 worker 将画廊打包并迁移至冷存储时，底层自动调用操作系统的 `statvfs` 实时查询各个归档根目录的剩余可用磁盘空间，**优先选择当前空闲容量最充裕的挂载盘写入**。无需人工手动为各硬盘拆分目录。
- **安全反向清理**：在设置页存储面板点击「清理已归档源目录」（`POST /api/system/purge-archived-sources`），系统自动核对冷存储各挂载卷中的 CBZ 与热下载目录中的原始文件夹，主动跳过正处于 `pending` / `downloading` 状态的活跃画廊，安全物理删除已归档画廊的解压散图源目录并即时核减磁盘占用。

### 2. 英文固定命名规范 (`gid-gallery.title.cbz`)
- **跨平台与备份兼容**：冷归档 CBZ 文件名统一强制采用 `gid-gallery.title.cbz` 命名模式（优先提取 ExHentai 官方英文/罗马音标题，彻底替换多字节特殊符号与非法字符）。
- **杜绝乱码与协议断流**：相比日文原名，英文 canonical 标题在 Linux ext4、Windows NTFS、macOS APFS 以及跨网络文件系统（NFS / SMB / WebDAV / rsync）与网盘备份工具同步时，彻底免除了字符集转义错误、编码不一致与不可读乱码风险。
- **243 字节上限对齐**：文件名严格控制在 243 字节以内（为临时打包后缀 `.cbz.partial` 预留 12 字节），保证总长绝不突破 Linux 255 字节上限，彻底规避 `[Errno 36] File name too long`。

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

- **参数说明**：
  - `--archive-dir`：待检查与修复的目标归档或画廊根目录路径（必填）。
  - `--dry-run`：仅执行模拟检查并打印清洗预览，不实际修改或重命名磁盘文件。
  - `--batch-size`：批量回查 GData 官方接口的分片大小（默认 25，严格遵守 ExHentai 限流）。

- **使用方法**：
  在宿主机直接执行（本地开发或宿主环境）：
  ```bash
  # 1. 演练模式（Dry Run）：仅检查并输出清洗预览，不实际修改文件
  python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive --dry-run

  # 2. 正式执行：批量剥离冗余 GID、重构索引并清洗冷库文件
  python backend/galleryvault/scripts/repair_cold_archives.py --archive-dir /path/to/archive
  ```

  **在 Docker 容器内一行执行（推荐生产运维方式）**：
  ```bash
  # 演练预览（注意将 /archive 替换为容器内挂载的实际冷存储路径）：
  docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive --dry-run

  # 正式执行清洗重构：
  docker compose exec backend python /app/galleryvault/scripts/repair_cold_archives.py --archive-dir /archive
  ```

### 2. CBZ 超长文件名对齐工具 (`repair_cbz_filenames.py`)

脚本位于 `scripts/repair_cbz_filenames.py`，专门解决历史旧归档在 Linux ext4 文件系统上因多字节字符超长导致的报错。

- **核心功能**：
  - **243 字节上限对齐**：遍历目标归档目录，对所有历史旧 CBZ 文件自动应用 Linux ext4 243 字节文件名截断规范（为 `.cbz.partial` 预留 12 字节，保证总文件名 ≤ 255 字节）。
  - **彻底消灭 Errno 36**：消除中日韩多字节特殊符号引发的 `[Errno 36] File name too long`，确保归档包在移动、备份或网盘同步时保持高度兼容。

- **参数说明**：
  - `--target-dir`：待扫描并对齐旧 CBZ 文件名的目录路径（必填）。
  - `--max-bytes`：文件名最大字节数（默认 243 字节）。
  - `--dry-run`：仅预览拟重命名列表，不改写磁盘文件。

- **使用方法**：
  在宿主机直接执行：
  ```bash
  # 扫描并自动规范化对齐旧 CBZ 归档文件名
  python scripts/repair_cbz_filenames.py --target-dir /path/to/archive
  ```

  **不要在容器里跑 `/app/scripts/repair_cbz_filenames.py`**（镜像未拷贝仓库根 `scripts/`）。在宿主机对挂载目录执行上一节命令。容器内清洗用上面的 `repair_cold_archives.py`。
