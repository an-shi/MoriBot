# 数据迁移与备份

MoriBot 从第一版开始就把**所有运行中产生的数据**放在同一个数据目录中，并把「导出 / 导入」设计成同一种可验证的 ZIP 归档。这样后续新增模型配置、角色卡、模型记忆、系统设置时，只要写入 `data/`，就会自动进入备份，不需要再改迁移代码。

## 1. 什么会被迁移

默认包含 `data/` 下除以下内容之外的全部文件：

- `logs/`：系统日志（明确不迁移）
- `initial_admin.txt`：一次性明文初始密码
- `backups/`、`tmp/`：临时文件和历史备份，避免递归
- SQLite 的 `-wal` / `-shm`：由在线快照替代
- `__pycache__/`、`.git/` 等缓存

数据库不是简单复制文件，而是通过 SQLite 的在线备份 API 生成一致性快照，因此**服务运行中也能够导出**。

归档结构：

```text
moribot-backup-20261112-103000.zip
├── manifest.json       # 格式版本、创建时间、每个文件的 SHA-256
├── config.json         # 系统设置、JWT 密钥、模型配置等未来配置
├── moribot.db          # 账户、模型、角色卡、记忆等数据库数据
└── plugins/...         # 插件代码与插件数据
    uploads/...         # 未来新增的上传文件（自动包含）
    ...                 # 未来任何 data/ 下的新数据
```

> 备份中包含密码哈希、JWT 密钥、角色卡与模型配置等敏感信息。请把它当成机密文件保管，传输时使用 HTTPS / SFTP / 加密磁盘，不要上传到公开网盘。

> 校验和用于发现传输损坏，不代表来源可信。请只导入自己生成的备份；恶意的归档可能包含会被加载的插件代码。

> 项目根目录的 `.env` 不属于 `data/`，不会自动进入备份。如果部署依赖其中的覆盖项，请单独迁移或在目标机器重新配置。

## 2. 导出

### 方式 A：控制台按钮

首页右上角点击「导出数据」，浏览器会下载：

```text
moribot-backup-YYYYMMDD-HHMMSS.zip
```

该接口需要已登录后台，返回 `Cache-Control: no-store`。

### 方式 B：API

```http
GET /api/v1/system/backup/export
Authorization: Bearer <dashboard_jwt>
```

```bash
curl -H "Authorization: Bearer $TOKEN" \
     -o moribot-backup.zip \
     http://127.0.0.1:6186/api/v1/system/backup/export
```

### 方式 C：命令行（无需启动服务）

```bash
uv run moribot backup export
# 指定路径
uv run moribot backup export --output /path/to/moribot-backup.zip
```

命令行导出会确保 `config.json` 存在，因此即使数据目录是全新的也能得到可导入的归档。

## 3. 导入

导入会替换目标数据目录，必须在 MoriBot 停止运行后执行：

```bash
# 1. 停止 MoriBot（Ctrl+C 或停止 systemd/docker 服务）

# 2. 导入到默认 data/ 目录
uv run moribot backup import /path/to/moribot-backup.zip

# 或指定数据目录
uv run moribot --data-dir /srv/moribot/data \
  backup import /path/to/moribot-backup.zip --yes

# 3. 重新启动
uv run main.py
```

导入流程：

1. 检查 ZIP 和 `manifest.json` 是否存在、格式版本是否支持。
2. 拒绝绝对路径、`..`、符号链接等不安全条目。
3. 校验每个文件的大小和 SHA-256。
4. 校验 `config.json` 可解析、SQLite 通过 `PRAGMA integrity_check`。
5. 解压到数据目录旁边的临时目录。
6. 把现有数据目录重命名为 `data.pre-import-<时间戳>`（保留回滚点）。
7. 原子替换为新目录；失败时自动恢复旧目录。
8. 日志目录会在下次启动时自动创建。

当前数据目录会被保留，例如：

```text
data/
data.pre-import-20261112-104500/
```

确认新数据无误后，可以手动删除旧目录；如果导入失败或需要回滚，把旧目录改回 `data/` 即可。

## 4. 迁移到另一台机器

1. 在新机器安装 Python 3.12、`uv`、Node/pnpm（如果需要在本地构建前端）。
2. 拉取 MoriBot 代码并执行 `uv sync`。
3. 复制备份 ZIP 到新机器。
4. 停止新机器上的 MoriBot（如果已启动过），执行 `backup import`。
5. 启动 MoriBot。

迁移后保持不变：

- 管理员用户名与密码哈希（原密码仍可登录）
- JWT 密钥（如果迁移前签发的 token 尚未过期，仍然有效）
- 模型 / 平台 / 系统配置
- 三类模型配置及加密后的 API Key（依赖 `config.json` 中的 JWT 密钥解密）
- 角色卡、人物设定、头像文件
- 模型记忆与业务数据（未来写入数据库或 `data/` 后自动包含）
- MoriMobile 已配对设备（设备令牌和哈希都在数据库中）

不迁移：

- 系统日志（避免把旧日志带到新环境）
- `initial_admin.txt`（一次性明文凭据；账户本体在数据库中）
- 插件通过 pip 安装的第三方依赖。插件代码会被迁移，但依赖需要在新机器重新安装，建议在插件目录中附带 `requirements.txt`。

## 5. 新增数据时如何保证可迁移

新功能只需要遵守一条约定：

> **所有需要跨机器恢复的运行数据，必须写入 `AppPaths.data_dir`。**

- 配置：写入 `data/config.json`（`ConfigManager`）
- 结构化数据：新增 SQLModel 表（自动进入 `moribot.db` 快照）
- 上传文件 / 模型缓存 / 记忆文件：放在 `data/uploads`、`data/memory` 等子目录
- 临时文件：放在 `data/tmp`（不进入备份）
- 系统日志：放在 `data/logs`（不进入备份）

不要在代码目录、用户主目录或系统临时目录保存唯一副本。这样备份逻辑永远不需要逐个功能修改。

## 6. 完整性校验与故障处理

- 档案里的每个文件都有 `size` 和 `sha256`，导入时会逐个校验。
- 数据库通过 SQLite 完整性检查。
- 不信任 ZIP 内的路径，防止 Zip Slip。
- 导入失败不会破坏现有数据：旧目录在替换成功前不会被删除。
- 当前备份是未加密 ZIP。需要离线保存时，建议使用加密磁盘或操作系统的磁盘加密；如果未来需要「带密码的备份」，可以在现有格式上增加加密层，而不改变数据内容。

## 7. 命令速查

```bash
# 导出
uv run moribot backup export
uv run moribot backup export -o /backups/moribot.zip

# 导入（服务已停止）
uv run moribot backup import /backups/moribot.zip --yes

# 重置管理员密码（不依赖备份）
uv run main.py --reset-password
```
