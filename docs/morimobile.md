# MoriMobile 网关设计

MoriMobile 是 MoriBot 的官方手机客户端，仓库：[an-shi/MoriMobile](https://github.com/an-shi/MoriMobile)。本仓库只包含服务端后台，不包含手机 App。MoriBot 不计划接入 QQ、Telegram、Discord 等第三方 IM。

目标是在手机不处于家庭局域网、家庭服务器位于 NAT 后面时，仍然可以双向传递消息，并为手机提供常规业务接口。

## 1. 连接方向

```text
┌────────────┐    HTTPS 配对 / 业务 API    ┌──────────────────────────┐
│ MoriMobile │ ──────────────────────────► │ /api/v1/mobile/pair      │
│  手机 App  │ ◄────────────────────────── │ /api/v1/mobile/app/*     │
└─────┬──────┘        设备令牌              └──────────────────────────┘
      │
      │ 出站 WSS + Bearer device token（仅实时聊天/推送）
      ▼
┌──────────────────────────────────────────────────────────────┐
│ MoriBot                                                      │
│  /api/v1/mobile/ws  ──► MobilePlatformAdapter                │
│                              │                               │
│                              ▼                               │
│                        EventBus → Pipeline                   │
└──────────────────────────────────────────────────────────────┘
```

- 手机始终作为客户端主动连接；服务端不主动拨号到手机。
- 常规业务走 HTTPS JSON API，实时聊天、流式回复和推送走 WSS。
- 服务端不需要保存手机公网 IP；家庭网络可通过隧道暴露一个 HTTPS/WSS 入口。
- 一条 WebSocket 连接承载上行消息、下行消息、心跳和撤销通知。

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

后续会话列表、历史记录、模型设置、文件上传等接口统一放在 `/api/v1/mobile/app/*`，后端依赖 `get_mobile_auth_context`。后台 JWT 不能用于这些接口，设备令牌也不能用于后台管理接口。

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

## 3. WebSocket 实时通道协议

WebSocket 只承载实时聊天、流式输出、ACK、心跳和推送；设备信息、历史记录、设置等常规业务使用上文的 HTTPS API。

### 3.1 连接

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

### 3.2 上行消息

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

然后进入事件总线和管道。后续的 Provider / Agent 回复通过 `MobilePlatformAdapter.send_message(device_id, text)` 下行。

### 3.3 下行消息

```json
{
  "type": "message",
  "id": "<uuid>",
  "text": "这是回复",
  "timestamp": 1762900000.0
}
```

### 3.4 心跳与错误

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

## 4. 安全边界

- 配对码生成：需要后台 JWT。
- 设备接入：需要高熵设备令牌，数据库只存哈希。
- **HTTP 业务接口**：`/api/v1/mobile/app/*` 只接受设备令牌；后台 JWT 与设备令牌不互通。
- 浏览器 Origin：若带 Origin 头，必须匹配 `cors_origins`、`public_url` 或当前 Host。
- 撤销：数据库立即失效 + WebSocket 强制关闭，后续 HTTP 请求同样被拒绝。
- 传输：生产环境必须使用 HTTPS/WSS（由反向代理或隧道终止 TLS）。
- 消息大小：服务端和客户端都应限制，避免内存放大攻击。

## 5. 当前限制与后续演进

- 设备离线时消息不排队；后续可以加持久化离线队列。
- 目前回复链路依赖后续的 Provider/Agent 阶段；网关本身已经完成上下行和事件接入。
- 暂未实现端到端加密，依赖 TLS；原因见部署文档。
- 未来可以增加设备级消息历史、推送通知（APNs/FCM）和二维码配对页面。
- 不计划支持 QQ、Telegram、Discord 等第三方平台；MoriMobile 是唯一官方客户端。
