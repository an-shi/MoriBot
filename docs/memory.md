# 角色记忆（MoriMemory）

MoriBot 使用 [MoriMemory](https://github.com/an-shi/MoriMemory) 作为本地优先的角色记忆引擎。MoriBot 负责启动和托管服务、在回复前召回记忆、在回复后异步写入记忆；MoriMemory 负责提取、去重、矛盾检测、检索和持久化。

记忆数据完全位于 MoriBot 数据目录的 `data/memory/` 下，随现有 ZIP 备份和数据目录迁移一起移动。

## 1. 架构

```text
MoriMobile / MoriBot 后台
  └─ MoriBot FastAPI
       ├─ MobileChatService
       │    ├─ 回复前 POST /api/v1/context（角色 + 会话）
       │    └─ 回复后 POST /api/v1/conversations/ingest（异步任务）
       ├─ /api/v1/memory/* 代理（JWT 鉴权）
       └─ MemoryServiceManager
            └─ MoriMemory 127.0.0.1:6190
                 └─ data/memory/morimemory.db
```

- MoriMemory 只监听 `127.0.0.1`，不直接暴露给手机或浏览器。
- 浏览器和 MoriMobile 都不接触 MoriMemory 服务令牌。
- MoriBot 的健康检查、召回和写入都使用 `data/memory/service-token` 中的高熵令牌。

## 2. 角色隔离

每个角色拥有独立的 `character:<角色 ID>` 空间：

| 内容 | 写入空间 | 其他角色可见 |
| --- | --- | --- |
| 用户的身份、偏好、事实、目标等长期记忆 | 当前角色空间 | 否 |
| 角色自身设定、推断、总结 | 当前角色空间 | 否 |
| 当天事件、情境等短期/情景记忆 | 当前会话空间（带角色 ID） | 否 |
| 同一角色过去的会话记忆 | 该角色自己的旧会话空间 | 仅同一角色可召回 |
| 共享用户空间 | 不自动写入 | 否 |

严格隔离规则由 MoriMemory 后端强制执行，不依赖前端过滤：

1. 带 `X-Mori-Character-Id` 的提取请求，所有 `auto` / `user` 作用域的记忆都会改写为 `character` 作用域。
2. `recall` 模式不会隐式读取用户空间。
3. 会话空间只能被当前会话或同一 `character_id` 读取；不同角色即使属于同一用户也无法互相读取。
4. 管理员在 `manage` 模式可以浏览全部角色空间，这是后台管理视图，不参与角色回复。
5. 如确实需要跨角色共享，必须通过 MoriMemory `/api/v1/grants` 显式授权。

## 3. 配置

`data/config.json`：

```json
{
  "memory": {
    "enabled": true,
    "auto_start": true,
    "auto_restart": true,
    "home": "",
    "host": "127.0.0.1",
    "port": 6190,
    "service_token": "",
    "startup_timeout_seconds": 30,
    "request_timeout_seconds": 120,
    "recall": {
      "enabled": true,
      "limit": 8,
      "token_budget": 1600,
      "timeout_seconds": 8
    },
    "ingest": {
      "enabled": true,
      "timeout_seconds": 15
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否启用记忆；关闭后聊天正常继续，只是不使用记忆 |
| `auto_start` | 是否由 MoriBot 启动 MoriMemory |
| `auto_restart` | 服务异常退出后是否自动重启 |
| `home` | MoriMemory 源码目录；留空时查找 `MORIMEMORY_HOME`，再查找 MoriBot 同级 `../MoriMemory` |
| `port` | 本地服务端口，默认 `6190` |
| `service_token` | 留空时自动生成到 `data/memory/service-token` |
| `recall.timeout_seconds` | 召回超时；超时只跳过记忆，不影响回复 |
| `ingest.timeout_seconds` | 入队超时；失败只记录日志 |

后台「系统设置 → 角色记忆」可以开关记忆和自动启动。修改后立即生效，无需重启 MoriBot。

## 4. 回复流程

`MobileChatService.send_message()`：

1. 校验会话归属和角色可用性。
2. 用当前用户消息调用 MoriMemory `POST /api/v1/context`：
   - `X-Mori-User-Id`：MoriBot 用户名
   - `X-Mori-Character-Id`：角色 ID
   - `X-Mori-Conversation-Id`：会话 UUID
   - `mode=recall`、`limit=8`、`token_budget=1600`、`record_access=true`
3. 将返回的 `context` 追加到系统提示词，并明确标注：这是历史记忆，不是本轮用户输入；冲突时以当前消息为准。
4. 调用对话模型生成回复，并持久化用户消息和助手消息。
5. 通过后台任务调用 `POST /api/v1/conversations/ingest`，提交本轮两条消息：
   - `async_mode=true`
   - 消息 ID 使用 MoriBot 数据库中的消息 ID
   - 提取失败不会影响已返回的回复
6. 同一 `client_message_id` 的重试直接返回已保存消息，不会再次调用模型或重复写入记忆。

记忆服务不可用时，召回和写入都会静默降级；聊天主流程不受影响。

## 5. 数据与迁移

```text
data/
├── config.json                 # memory 配置
└── memory/
    ├── config.json             # MoriMemory 配置
    ├── morimemory.db           # SQLite + FTS5 + 向量
    ├── service-token           # 服务令牌
    ├── memory-service.lock     # 进程锁
    ├── memory-service.out.log  # 启动输出
    └── logs/                   # MoriMemory 日志
```

- 备份会包含 `data/memory/config.json`、`morimemory.db` 和 `service-token`。
- 进程锁、启动输出和 MoriMemory 日志不会进入备份，避免迁移后误判旧进程仍在运行。
- 迁移到新机器后，MoriBot 会使用同一份令牌和数据库启动服务。
- `data/memory/service-token` 属于敏感文件，不要单独提交到 Git。

## 6. API

MoriBot 代理（需要后台 JWT）：

```http
GET    /api/v1/memory/health
GET    /api/v1/memory/spaces?kind=character
GET    /api/v1/memory/memories?space_id=...&q=...
DELETE /api/v1/memory/memories/{memory_id}
```

代理会自动注入：

```http
X-Mori-User-Id: <当前后台用户名>
X-Mori-Role: admin
```

并透传：

```http
X-Mori-Character-Id
X-Mori-Conversation-Id
```

角色名称通过 ingest 请求体中的 `character_name` 传递，不放在 HTTP 头中，避免中文名称触发 ASCII 编码错误。

MoriMemory 其余管理接口同样可以通过 `/api/v1/memory/*` 使用，例如配置、图谱、导入导出和任务管理。

## 7. 后台页面

左侧「记忆」页面按角色空间展示：

- 角色空间列表和每个空间的记忆数量
- 当前角色的记忆内容、分类、来源、重要度、更新时间
- 在当前角色空间内搜索
- 删除单条记忆
- 记忆引擎版本与 FTS5 状态

页面只展示 `character` 类型的空间，避免把管理员视图和角色召回混在一起。

## 8. 故障排查

| 现象 | 检查 |
| --- | --- |
| 启动日志提示 MoriMemory 不可用 | 确认 `../MoriMemory` 存在，或设置 `memory.home` / `MORIMEMORY_HOME` |
| `data/memory/memory-service.out.log` 有错误 | 检查 MoriMemory 依赖是否安装、端口 `6190` 是否被占用 |
| 记忆页面 503 | 记忆服务未启动或 `memory.enabled=false` |
| 角色没有记忆 | 确认角色已启用、对话消息足够长；MoriMemory 默认只提取 user 消息 |
| 另一个角色看不到记忆 | 这是预期行为；严格隔离禁止跨角色读取 |
| 想清空角色记忆 | 在「记忆」页面删除，或通过 `/api/v1/memory/memories/{id}` 删除 |
