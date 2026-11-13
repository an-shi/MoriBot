# MoriMobile 对接文档

MoriMobile 是 MoriBot 的官方手机客户端，仓库：[an-shi/MoriMobile](https://github.com/an-shi/MoriMobile)。本仓库只包含服务端后台，不包含手机 App。MoriBot 不计划接入 QQ、Telegram、Discord 等第三方 IM。

目标是在手机不处于家庭局域网、家庭服务器位于 NAT 后面时，仍然可以双向传递消息，并为手机提供常规业务接口。MoriBot 不保存会话；手机本地维护角色绑定和完整聊天历史，每次生成回复时把当前上下文发给 MoriBot。

## 1. 连接方向

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
│  /api/v1/mobile/app/chat ──► ModelGateway ──► 模型供应商      │
│  /api/v1/mobile/ws       ──► MobilePlatformAdapter           │
│                              │                               │
│                              ▼                               │
│                        EventBus → Pipeline                   │
└──────────────────────────────────────────────────────────────┘
```

- 手机始终作为客户端主动连接；服务端不主动拨号到手机。
- 对话生成、角色卡、设备信息等常规业务走 HTTPS JSON API。
- WSS 用于服务端事件、推送、心跳和连接状态；对话请求不使用 WebSocket。
- 服务端不需要保存手机公网 IP；家庭网络可通过隧道暴露一个 HTTPS/WSS 入口。
- MoriBot 不保存对话内容；手机负责本地历史和界面展示。

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

### 2.3 设备 HTTP 业务接口

常规业务接口使用设备令牌认证，与后台管理 JWT 完全分离：

```http
GET /api/v1/mobile/app/me
Authorization: Bearer mm_...
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

MoriMobile 业务接口统一放在 `/api/v1/mobile/app/*`，后端依赖 `get_mobile_auth_context`。后台 JWT 不能用于这些接口，设备令牌也不能用于后台管理接口。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/mobile/app/me` | 校验设备并返回设备/账户信息 |
| `GET` | `/api/v1/mobile/app/characters` | 获取可在手机上使用的角色卡 |
| `POST` | `/api/v1/mobile/app/chat` | 根据本地历史生成一条角色回复 |

角色卡和对话接口详见第 3 节。

### 2.4 设备管理（后台 JWT）

```http
GET  /api/v1/mobile/devices
POST /api/v1/mobile/devices/{device_id}/message
POST /api/v1/mobile/devices/{device_id}/revoke
```

向在线设备发送消息：

```http
POST /api/v1/mobile/devices/{device_id}/message
Authorization: Bearer <dashboard_jwt>
Content-Type: application/json

{"text": "记得带伞"}
```

在线设备会收到 `{"type":"message","text":"记得带伞",...}`。设备离线时返回 `409`。

撤销后服务端会向该设备的 WebSocket 发送 `revoked`，随后以 `4001` 关闭连接。

## 3. 对话接口

### 3.1 设计约定

- 角色卡只在 MoriBot 后台维护；手机保存 `character_id` 和本地聊天历史。
- MoriBot 不保存任何对话内容。手机每次发送当前上下文，服务端只生成一条新回复。
- 角色卡的 `chat_provider_id`、`speech_provider_id`、`image_provider_id` 为 `null` 时，分别使用该类别的系统默认模型。
- 角色卡显式指定了 Provider，但该 Provider 已停用或不存在时返回 `409`，不会静默切换到其他模型。
- `GET /app/characters` 只返回 `enabled=true` 的角色卡。`chat_available=false` 表示服务端当前没有可用的对话模型。
- 头像字段是相对路径，例如 `/avatars/3f2a.png`。手机用配对时保存的服务端根地址拼接后展示。
- 人物设定 `persona` 只在服务端使用，不通过列表接口下发。

### 3.2 获取角色卡列表

```http
GET /api/v1/mobile/app/characters
Authorization: Bearer mm_...
```

响应：

```json
{
  "status": "ok",
  "message": null,
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

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int | 角色卡 ID，对话时作为 `character_id` |
| `name` | string | 角色名 |
| `avatar` | string | 头像相对路径，可能为空 |
| `description` | string | 角色简介，可能为空 |
| `chat_available` | bool | 是否有可用的对话模型 |
| `speech_available` | bool | 是否可用语音回复 |
| `image_available` | bool | 是否可用图片生成 |
| `updated_at` | string | 角色卡最后更新时间，可用于缓存失效 |

### 3.3 生成一条回复

```http
POST /api/v1/mobile/app/chat
Authorization: Bearer mm_...
Content-Type: application/json
```

请求：

```json
{
  "character_id": 1,
  "client_message_id": "local-42",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "在的，今天怎么样？"},
    {"role": "user", "content": "今天有点累"}
  ],
  "speech": false
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `character_id` | int | 是 | 角色卡 ID |
| `messages` | array | 是 | 按时间顺序排列的上下文，1–200 条 |
| `messages[].role` | string | 是 | 只能是 `user` 或 `assistant` |
| `messages[].content` | string | 是 | 消息正文，单条最多 8000 字符 |
| `client_message_id` | string | 否 | 客户端消息 ID，原样回传，最多 128 字符；不做去重 |
| `speech` | bool | 否 | 为 `true` 时强制生成语音回复，默认 `false` |

约束：

- 最后一条消息必须是 `user`，否则返回 `400`。
- `system` 消息不允许由客户端传入；服务端会根据角色卡的名称、简介和 `persona` 自动生成系统提示词。
- `messages` 中的空白消息会被拒绝。
- `client_message_id` 为空时，服务端会生成一个 UUID 并在响应中返回。
- 服务端不保存请求内容，重试会重新调用模型。`client_message_id` 只用于让手机把响应和本地消息对应起来。

响应：

```json
{
  "status": "ok",
  "message": null,
  "data": {
    "client_message_id": "local-42",
    "character_id": 1,
    "text": "辛苦啦，先缓一缓。要不要说说今天发生了什么？",
    "speech": null,
    "images": [],
    "chat_model": {
      "provider_id": "3",
      "model": "gpt-4.1-mini"
    },
    "created_at": "2026-11-13T09:12:34.567890"
  }
}
```

带语音时：

```json
{
  "status": "ok",
  "data": {
    "client_message_id": "local-43",
    "character_id": 1,
    "text": "我在听。",
    "speech": {
      "mime_type": "audio/mpeg",
      "format": "mp3",
      "data_url": "data:audio/mpeg;base64,SUQzBAAAAAA...",
      "byte_length": 18432
    },
    "images": [],
    "chat_model": {"provider_id": "3", "model": "gpt-4.1-mini"},
    "created_at": "2026-11-13T09:13:00.123456"
  }
}
```

模型调用图片工具时，`images` 会包含生成结果：

```json
{
  "images": [
    {
      "mime_type": "image/png",
      "data_url": "data:image/png;base64,iVBORw0KGgo...",
      "url": null
    }
  ]
}
```

- `data_url` 可直接交给 Flutter 的 `Image.memory` / 音频播放器解码。
- 部分供应商可能只返回远程地址，此时 `data_url` 为 `null`，使用 `url`。
- `speech` 有两个来源：模型主动调用 `generate_speech` 工具，或请求里的 `speech=true` 强制合成。两者不会重复执行。
- 当前版本为一次性 JSON 响应，不是 SSE 流式输出；手机应先显示“正在输入”，收到响应后一次性替换。
- 模型调用可能持续数十秒，手机端 HTTP 超时建议不少于 120 秒。

### 3.4 时序

```text
MoriMobile                         MoriBot                          Model Provider
    │                                 │                                   │
    │ GET /app/characters             │                                   │
    │────────────────────────────────►│ 读取 character_cards              │
    │◄────────────────────────────────│ 只返回 enabled 角色               │
    │                                 │                                   │
    │ POST /app/chat                  │                                   │
    │  character_id + messages        │                                   │
    │────────────────────────────────►│ 校验角色/消息                     │
    │                                 │ 组装 system prompt                │
    │                                 │ 解析角色模型覆盖                  │
    │                                 │──── chat(messages, tools) ───────►│
    │                                 │◄──── text / tool_calls ───────────│
    │                                 │ 可选：speech / image 工具         │
    │                                 │──── synthesize/generate ─────────►│
    │                                 │◄──── audio / image ───────────────│
    │◄────────────────────────────────│ text + speech + images            │
    │ 写入本地历史并显示               │                                   │
```

### 3.5 错误响应

所有错误沿用统一信封：

```json
{
  "status": "error",
  "message": "角色卡不存在或已停用",
  "data": null
}
```

| HTTP 状态 | 场景 |
| --- | --- |
| `400` | 消息为空、最后一条不是用户消息、消息过长 |
| `401` | 设备令牌缺失、无效或设备已撤销 |
| `404` | 角色卡不存在或已停用 |
| `409` | 角色没有可用的对话模型；请求语音但未配置语音模型 |
| `422` | 请求体字段缺失、类型错误、超过 200 条消息 |
| `502` | 模型供应商请求失败、超时或返回错误 |
| `500` | 服务端内部错误 |

错误消息会根据 `Accept-Language` 或 `X-Mori-Locale` 返回中文或英文。

## 4. WebSocket 实时通道协议

WebSocket 用于服务端事件、推送、心跳和连接状态。对话生成使用第 3 节的 HTTPS 接口。WS 上行的 `message` 仍会转换为 `MoriEvent` 并进入事件总线，但服务端只返回 `ack`，不会自动生成对话回复；该路径保留给后续的实时事件扩展。

### 4.1 连接

```http
GET /api/v1/mobile/ws
Authorization: Bearer mm_...
```

也支持：

```http
X-Mori-Device-Token: mm_...
```

不支持把令牌放在 URL 查询参数中，避免被代理日志记录。

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

### 4.2 上行消息

```json
{
  "type": "message",
  "text": "你好 MoriBot",
  "client_message_id": "local-42"
}
```

服务端确认：

```json
{
  "type": "ack",
  "client_message_id": "local-42",
  "timestamp": 1762900000.0
}
```

服务端会把消息转换为：

```text
MoriEvent(
  type=message,
  platform_id="morimobile",
  platform_name="MoriMobile",
  session_id=<device_id>,
  sender_id=<device_id>,
  sender_name=<device_name>,
  message=<text>,
  extras={mobile_device_id, client_message_id}
)
```

然后进入事件总线和管道。此路径目前只做事件投递，不会生成模型回复；需要对话回复时请调用 `POST /api/v1/mobile/app/chat`。

### 4.3 下行消息

```json
{
  "type": "message",
  "id": "<uuid>",
  "text": "这是回复",
  "timestamp": 1762900000.0
}
```

### 4.4 心跳与错误

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

## 5. 安全边界

- 配对码生成：需要后台 JWT。
- 设备接入：需要高熵设备令牌，数据库只存哈希。
- **HTTP 业务接口**：`/api/v1/mobile/app/*` 只接受设备令牌；后台 JWT 与设备令牌不互通。
- 浏览器 Origin：若带 Origin 头，必须匹配 `cors_origins`、`public_url` 或当前 Host。
- 撤销：数据库立即失效 + WebSocket 强制关闭，后续 HTTP 请求同样被拒绝。
- 传输：生产环境必须使用 HTTPS/WSS（由反向代理或隧道终止 TLS）。
- 消息大小：服务端和客户端都应限制，避免内存放大攻击。

## 6. 当前限制与后续演进

- 对话历史完全由手机维护；MoriBot 不保存、不检索、不迁移会话。
- 对话接口目前是一次性 JSON 响应，暂未提供 SSE / WSS 流式输出。
- 消息输入目前只支持文本；图片输入需要后续扩展多模态消息结构。
- 设备离线时服务端推送不排队；后续可以加持久化离线队列。
- 暂未实现端到端加密，依赖 TLS；原因见部署文档。
- 未来可以增加语音消息、图片输入、推送通知（APNs/FCM）和二维码配对页面。
- 不计划支持 QQ、Telegram、Discord 等第三方平台；MoriMobile 是唯一官方客户端。
