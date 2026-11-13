# MoriMobile 对接文档

MoriMobile 是 MoriBot 的官方手机客户端，仓库：[an-shi/MoriMobile](https://github.com/an-shi/MoriMobile)。本仓库只包含服务端后台，不包含手机 App。MoriBot 不计划接入 QQ、Telegram、Discord 等第三方 IM。

MoriBot 是角色卡、会话、消息和生成媒体的**唯一数据源**。手机本地只保留缓存，用于快速启动、离线查看和减少重复请求；缓存可以随时丢弃并从 MoriBot 重新同步。

## 1. 数据归属与连接方向

```text
┌────────────┐    HTTPS 配对 / 业务 API    ┌──────────────────────────┐
│ MoriMobile │ ──────────────────────────► │ /api/v1/mobile/pair      │
│  手机 App  │ ◄────────────────────────── │ /api/v1/mobile/app/*     │
└─────┬──────┘        设备令牌              └──────────────────────────┘
      │
      │ 出站 WSS + Bearer device token（服务端事件/推送）
      ▼
┌──────────────────────────────────────────────────────────────┐
│ MoriBot                                                      │
│  conversations / conversation_messages  ──► SQLite           │
│  data/media/<user_id>/                   ──► 语音、图片文件   │
│  ModelGateway                            ──► 模型供应商       │
│  /api/v1/mobile/ws                       ──► 事件与推送       │
└──────────────────────────────────────────────────────────────┘
```

- 手机始终作为客户端主动连接；服务端不主动拨号到手机。
- 角色卡、会话列表、消息历史、发送消息、媒体下载全部走 HTTPS JSON API。
- WSS 用于服务端事件、推送、心跳和连接状态，不承载常规 CRUD。
- MoriBot 保存全部对话内容和生成媒体；手机本地数据库只是可重建的缓存。
- 接入这套接口后，MoriMobile 不再直接保存模型供应商 API Key，也不直接调用模型供应商；对话模型由 MoriBot 按角色卡选择并调用。

## 2. 配对协议

### 2.1 创建配对码（需要后台登录）

```http
POST /api/v1/mobile/pairing-code
Authorization: Bearer <dashboard_jwt>
```

响应：

```json
{
  "status": "ok",
  "message": "配对码已生成，请在手机端输入",
  "data": {
    "code": "H63M-5LQF",
    "expires_at": "2026-11-12T02:43:07.066289",
    "pairing_uri": "morimobile://pair?server=https%3A%2F%2Fmori.example.com&code=H63M-5LQF",
    "server_url": "https://mori.example.com"
  }
}
```

- 配对码 8 位，去掉易混淆字符（`0/O/1/I`）。
- 10 分钟有效，单次使用。
- 生成接口需要已登录的管理员 JWT。
- 服务端只存 SHA-256，不存明文配对码。

### 2.2 手机兑换设备令牌

```http
POST /api/v1/mobile/pair
Content-Type: application/json

{
  "code": "H63M-5LQF",
  "device_name": "Pixel 9"
}
```

响应：

```json
{
  "status": "ok",
  "message": "设备配对成功",
  "data": {
    "device_token": "mm_1bIOH7-ux9yE4hCk2l1N4ruRmS9mRn8AYC7GbCgS0L4",
    "device": {
      "id": "03e6779c-d36f-4d3d-b9b2-a097680a092b",
      "name": "Pixel 9",
      "online": false,
      "created_at": "2026-11-12T02:33:19.386867",
      "last_seen_at": null,
      "revoked_at": null
    }
  }
}
```

- 设备令牌只返回一次，手机应写入 Keychain / Android Keystore。
- 服务端只存令牌的 SHA-256。
- 失败按 IP 限流（5 次 / 60 秒，锁定 120 秒）。
- 达到 `mobile.max_devices` 后拒绝新设备。

### 2.3 设备认证

所有 `/api/v1/mobile/app/*` 接口使用设备令牌认证：

```http
Authorization: Bearer mm_...
```

也支持：

```http
X-Mori-Device-Token: mm_...
```

后台管理 JWT 不能用于手机业务接口，设备令牌也不能用于后台管理接口。

### 2.4 校验设备与账户

```http
GET /api/v1/mobile/app/me
```

响应包含当前设备、绑定账户、服务端版本和协议版本：

```json
{
  "status": "ok",
  "data": {
    "device": {
      "id": "03e6779c-d36f-4d3d-b9b2-a097680a092b",
      "name": "Pixel 9",
      "online": true
    },
    "user": {
      "id": 1,
      "username": "admin",
      "display_name": "Administrator",
      "role": "admin"
    },
    "server_version": "0.1.0",
    "protocol": 1
  }
}
```

### 2.5 设备管理（后台 JWT）

```http
GET  /api/v1/mobile/devices
POST /api/v1/mobile/devices/{device_id}/message
POST /api/v1/mobile/devices/{device_id}/revoke
```

撤销后服务端会向该设备的 WebSocket 发送 `revoked`，随后以 `4001` 关闭连接；该设备的后续 HTTP 请求同样会被拒绝。

## 3. 手机端缓存策略

MoriBot 是数据源，手机缓存的目标是减少请求次数，而不是替代服务端存储。

推荐流程：

1. 启动或回到前台：调用 `/app/me` 校验令牌。
2. 本地有缓存时先展示缓存，同时刷新 `/app/characters` 和 `/app/conversations`。
3. 进入某个会话时，本地先展示缓存消息，再调用消息接口补齐。
4. 增量同步使用 `after_id`：只请求比本地最大消息 ID 更新的消息。
5. 需要查看更多历史时使用 `before_id` 向前翻页。
6. 发送消息成功后，用响应中的 `user_message` 和 `assistant_message` 更新本地缓存。
7. 下拉刷新或缓存版本变化时，重新拉取会话信息；服务端记录始终优先于本地记录。

缓存建议：

- 角色卡以 `updated_at` 判断是否变化。
- 会话以 `updated_at`、`message_count`、`last_message_at` 判断是否需要刷新。
- 消息以自增 `id` 作为唯一排序和增量游标。
- 媒体文件按 URL 文件名缓存，丢失时重新下载。
- 退出登录、设备被撤销或服务端返回 `401` 时，清空本地缓存。

## 4. 角色卡

```http
GET /api/v1/mobile/app/characters
Authorization: Bearer mm_...
```

响应：

```json
{
  "status": "ok",
  "data": [
    {
      "id": 1,
      "name": "Mori",
      "avatar": "/avatars/3f2a9c.png",
      "description": "安静、温柔的 AI 伙伴",
      "chat_available": true,
      "speech_available": true,
      "image_available": false,
      "updated_at": "2026-11-13T08:30:00"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int | 角色卡 ID，创建会话时使用 |
| `name` | string | 角色名 |
| `avatar` | string | 头像相对路径，可能为空 |
| `description` | string | 角色简介，可能为空 |
| `chat_available` | bool | 是否有可用的对话模型 |
| `speech_available` | bool | 是否可用语音回复 |
| `image_available` | bool | 是否可用图片生成 |
| `updated_at` | string | 角色卡最后更新时间 |

- 只返回 `enabled=true` 的角色卡。
- 人物设定 `persona` 不下发；服务端在生成回复时自动组装系统提示词。
- 头像相对路径需要拼接配对时保存的服务端根地址。

## 5. 会话

会话属于账户，而不是单个设备。同一账户配对的多个设备可以看到同一份会话和消息。列表按最近活动时间（`updated_at`）倒序排列。

### 5.1 会话列表

```http
GET /api/v1/mobile/app/conversations?character_id=1&limit=50&offset=0
```

查询参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `character_id` | 无 | 只返回该角色的会话 |
| `limit` | 50 | 1–100 |
| `offset` | 0 | 分页偏移 |

响应：

```json
{
  "status": "ok",
  "data": {
    "conversations": [
      {
        "id": "484d568bdd164385b96647654c370cf5",
        "character_id": 1,
        "character_name": "Mori",
        "character_avatar": "/avatars/3f2a9c.png",
        "character_available": true,
        "title": "今天有点累",
        "last_message_preview": "辛苦啦，先缓一缓。",
        "last_message_at": "2026-11-13T09:12:34.567890",
        "message_count": 12,
        "created_at": "2026-11-13T09:00:00",
        "updated_at": "2026-11-13T09:12:34.567890"
      }
    ],
    "has_more": false
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 会话 ID，后续消息接口使用 |
| `character_id` | 绑定的角色卡 |
| `character_name` / `character_avatar` | 当前角色信息；角色删除后名称使用创建时的快照，头像为空 |
| `character_available` | 角色是否仍存在且启用；为 `false` 时手机应禁用输入 |
| `title` | 会话标题，首次发送消息后自动生成，可手动修改 |
| `last_message_preview` | 最后一条回复的摘要 |
| `last_message_at` | 最后一条消息时间，用于排序和缓存失效 |
| `message_count` | 会话内消息数量 |
| `has_more` | 是否还有下一页会话 |

### 5.2 创建会话

```http
POST /api/v1/mobile/app/conversations
Content-Type: application/json

{
  "character_id": 1,
  "title": ""
}
```

`title` 可以为空；首次发送消息时服务端会用第一条用户消息自动生成标题。响应为单个会话对象。

### 5.3 会话详情

```http
GET /api/v1/mobile/app/conversations/{conversation_id}
```

### 5.4 重命名会话

```http
PATCH /api/v1/mobile/app/conversations/{conversation_id}
Content-Type: application/json

{"title": "晚间聊天"}
```

标题长度 1–100 字符。

### 5.5 删除会话

```http
DELETE /api/v1/mobile/app/conversations/{conversation_id}
```

删除会话会同时删除该会话的全部消息和本地生成的语音、图片文件。该操作不可恢复。

## 6. 消息

### 6.1 读取历史

```http
GET /api/v1/mobile/app/conversations/{conversation_id}/messages?limit=50
```

增量同步：

```http
GET /api/v1/mobile/app/conversations/{conversation_id}/messages?after_id=120
```

向前翻页：

```http
GET /api/v1/mobile/app/conversations/{conversation_id}/messages?before_id=80&limit=50
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `limit` | 50 | 1–100 |
| `before_id` | 无 | 返回 ID 小于该值的消息，用于查看更早历史 |
| `after_id` | 无 | 返回 ID 大于该值的消息，用于增量同步 |

`before_id` 和 `after_id` 不能同时使用。

响应：

```json
{
  "status": "ok",
  "data": {
    "messages": [
      {
        "id": 121,
        "conversation_id": "484d568bdd164385b96647654c370cf5",
        "role": "user",
        "content": "今天有点累",
        "speech": null,
        "images": [],
        "client_message_id": "local-42",
        "provider_id": "",
        "model": "",
        "created_at": "2026-11-13T09:12:33.123456"
      },
      {
        "id": 122,
        "conversation_id": "484d568bdd164385b96647654c370cf5",
        "role": "assistant",
        "content": "辛苦啦，先缓一缓。",
        "speech": {
          "url": "/api/v1/mobile/app/media/8f2a.mp3",
          "mime_type": "audio/mpeg",
          "format": "mp3",
          "byte_length": 18432
        },
        "images": [],
        "client_message_id": "local-42",
        "provider_id": "3",
        "model": "gpt-4.1-mini",
        "created_at": "2026-11-13T09:12:34.567890"
      }
    ],
    "has_more": false,
    "earliest_id": 121,
    "latest_id": 122
  }
}
```

分页说明：

- 消息始终按 `id` 升序返回。
- 不传游标时返回最新一页；`has_more=true` 表示还有更早的消息。
- 传 `after_id` 时返回更新的消息；`has_more=true` 表示还有更多新消息。
- 传 `before_id` 时返回更早的消息；`has_more=true` 表示还有更早的消息。
- `earliest_id` / `latest_id` 是当前页的首尾 ID，可直接用作下一次游标。

### 6.2 发送消息

```http
POST /api/v1/mobile/app/conversations/{conversation_id}/messages
Content-Type: application/json

{
  "content": "今天有点累",
  "client_message_id": "local-42",
  "speech": true
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `content` | string | 是 | 用户消息，1–8000 字符 |
| `client_message_id` | string | 否 | 客户端消息 ID，最多 128 字符；为空时服务端生成 UUID |
| `speech` | bool | 否 | 为 `true` 时强制生成语音回复，默认 `false` |

服务端行为：

1. 校验会话属于当前账户。
2. 读取该会话最近的持久化消息（最多 100 条、总字符不超过 60000）。
3. 根据角色卡的名称、简介和 `persona` 组装系统提示词。
4. 调用角色指定的对话模型；未指定时使用系统默认模型。
5. 模型可以调用 `generate_speech` / `generate_image` 工具。
6. 在同一个数据库事务中写入用户消息和助手回复。
7. 更新会话标题、消息数量、最后消息时间和摘要。

`client_message_id` 用于幂等重试：同一会话内重复提交相同 ID 时，服务端直接返回已经保存的两条消息，不会重复调用模型。

响应：

```json
{
  "status": "ok",
  "data": {
    "conversation": {
      "id": "484d568bdd164385b96647654c370cf5",
      "character_id": 1,
      "character_name": "Mori",
      "character_available": true,
      "title": "今天有点累",
      "last_message_preview": "辛苦啦，先缓一缓。",
      "last_message_at": "2026-11-13T09:12:34.567890",
      "message_count": 2,
      "created_at": "2026-11-13T09:00:00",
      "updated_at": "2026-11-13T09:12:34.567890"
    },
    "user_message": {
      "id": 121,
      "role": "user",
      "content": "今天有点累",
      "client_message_id": "local-42",
      "speech": null,
      "images": []
    },
    "assistant_message": {
      "id": 122,
      "role": "assistant",
      "content": "辛苦啦，先缓一缓。",
      "client_message_id": "local-42",
      "speech": {
        "url": "/api/v1/mobile/app/media/8f2a.mp3",
        "mime_type": "audio/mpeg",
        "format": "mp3",
        "byte_length": 18432
      },
      "images": [],
      "provider_id": "3",
      "model": "gpt-4.1-mini"
    }
  }
}
```

- 响应中同时返回 `user_message` 和 `assistant_message`，手机应直接用它们替换本地临时消息。
- 用户消息和助手消息带有相同的 `client_message_id`，便于关联。
- 模型生成图片时，`assistant_message.images` 会包含图片对象。
- 如果模型只生成了媒体而没有文字，`content` 可能为空。

### 6.3 时序

```text
MoriMobile                         MoriBot                          Model Provider
    │                                 │                                   │
    │ GET /app/conversations          │                                   │
    │────────────────────────────────►│ 查询 conversations                │
    │◄────────────────────────────────│ 会话摘要 + 缓存版本               │
    │                                 │                                   │
    │ GET .../messages?after_id=120   │                                   │
    │────────────────────────────────►│ 查询 conversation_messages        │
    │◄────────────────────────────────│ 增量消息                          │
    │                                 │                                   │
    │ POST .../messages               │                                   │
    │  content + client_message_id    │                                   │
    │────────────────────────────────►│ 校验归属 + 读取持久化历史         │
    │                                 │ 组装 system prompt                │
    │                                 │ 解析角色模型覆盖                  │
    │                                 │──── chat(messages, tools) ───────►│
    │                                 │◄──── text / tool_calls ───────────│
    │                                 │ 可选：speech / image 工具         │
    │                                 │ 写入用户消息 + 助手回复           │
    │                                 │ 更新会话摘要                      │
    │◄────────────────────────────────│ 会话 + 两条消息 + 媒体 URL        │
    │ 更新本地缓存并显示               │                                   │
```

## 7. 生成媒体

语音和图片保存在数据目录：

```text
data/media/<user_id>/<uuid>.mp3
data/media/<user_id>/<uuid>.png
```

接口只返回 URL，不在 JSON 中塞入 base64：

```json
{
  "speech": {
    "url": "/api/v1/mobile/app/media/8f2a.mp3",
    "mime_type": "audio/mpeg",
    "format": "mp3",
    "byte_length": 18432
  },
  "images": [
    {
      "url": "/api/v1/mobile/app/media/a91c.png",
      "mime_type": "image/png"
    }
  ]
}
```

下载媒体时必须带设备令牌：

```http
GET /api/v1/mobile/app/media/8f2a.mp3
Authorization: Bearer mm_...
```

- 媒体按账户隔离，只能下载自己账户目录下的文件。
- 文件名是随机 UUID，但不要依赖 URL 保密；鉴权仍然必须。
- 手机应把媒体下载到本地缓存目录；缓存丢失时可重新下载。
- 如果供应商只返回远程图片地址，`url` 可能是 `https://...`，手机直接加载并缓存。

## 8. WebSocket 实时通道协议

WebSocket 用于服务端事件、推送、心跳和连接状态。会话与消息操作使用上文的 HTTPS 接口。

WS 上行的 `message` 仍会转换为 `MoriEvent` 并进入事件总线，但服务端只返回 `ack`，不会自动生成对话回复；该路径保留给后续实时事件扩展。

### 8.1 连接

```http
GET /api/v1/mobile/ws
Authorization: Bearer mm_...
```

连接成功后服务端发送：

```json
{
  "type": "hello",
  "protocol": 1,
  "server": "MoriBot",
  "server_version": "0.1.0",
  "device_id": "03e...",
  "device_name": "Pixel 9",
  "heartbeat_seconds": 25,
  "max_text_chars": 8000
}
```

### 8.2 心跳与错误

- 服务端每 25 秒发送 `{"type":"ping"}`，手机应回复 `{"type":"pong"}`。
- 75 秒没有任何上行数据，服务端关闭连接。
- 上行单帧最大 64 KiB，文本最大 8000 字符。
- 错误帧：

```json
{
  "type": "error",
  "code": "invalid_message",
  "message": "消息格式无效"
}
```

## 9. 错误响应

所有错误沿用统一信封：

```json
{
  "status": "error",
  "message": "会话不存在或无权访问",
  "data": null
}
```

| HTTP 状态 | 场景 |
| --- | --- |
| `400` | 消息为空、消息过长、分页游标冲突、标题为空 |
| `401` | 设备令牌缺失、无效或设备已撤销 |
| `404` | 角色卡、会话或媒体文件不存在；会话不属于当前账户 |
| `409` | 角色没有可用的对话模型；请求语音但未配置语音模型；消息重复但回复缺失 |
| `422` | 请求体字段缺失、类型错误、超出分页或长度限制 |
| `502` | 模型供应商请求失败、超时或返回错误 |
| `500` | 服务端内部错误 |

错误消息会根据 `Accept-Language` 或 `X-Mori-Locale` 返回中文或英文。

## 10. 数据存储与迁移

MoriBot 的运行数据都在同一个数据目录中：

```text
data/
├── moribot.db                 # 账户、模型、角色卡、会话、消息
├── media/<user_id>/           # 生成的语音和图片
├── avatars/                   # 角色头像
├── plugins/                   # 插件
└── config.json                # 系统配置与加密密钥
```

- 会话保存在 `conversations` 表，消息保存在 `conversation_messages` 表。
- 数据库备份使用 SQLite 在线快照，`data/media/` 等文件按原路径进入备份 ZIP。
- 导出后在新的 MoriBot 实例导入，会话、消息、媒体和角色头像都会一起恢复。
- 手机本地缓存不属于迁移范围；换机后重新同步即可。
- 删除会话时对应的本地媒体文件也会删除。

## 11. 安全边界

- 配对码生成：需要后台 JWT。
- 设备接入：需要高熵设备令牌，数据库只存哈希。
- **HTTP 业务接口**：`/api/v1/mobile/app/*` 只接受设备令牌；后台 JWT 与设备令牌不互通。
- **会话归属**：所有查询和写入都会校验 `user_id`，不同账户不能读取彼此的会话或媒体。
- 浏览器 Origin：若带 Origin 头，必须匹配 `cors_origins`、`public_url` 或当前 Host。
- 撤销：数据库立即失效 + WebSocket 强制关闭，后续 HTTP 请求同样被拒绝。
- 传输：生产环境必须使用 HTTPS/WSS（由反向代理或隧道终止 TLS）。

## 12. 当前限制与后续演进

- 对话接口目前是一次性 JSON 响应，暂未提供 SSE / WSS 流式输出。
- 消息输入目前只支持文本；图片输入需要后续扩展多模态消息结构。
- 模型上下文默认取最近 100 条消息、总计不超过 60000 字符。
- 设备离线时服务端推送不排队；手机可先显示缓存，联网后重试发送。
- 未来可以增加消息重生成、消息删除、会话归档、推送通知（APNs/FCM）和二维码配对页面。
- 不计划支持 QQ、Telegram、Discord 等第三方平台；MoriMobile 是唯一官方客户端。
