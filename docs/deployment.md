# MoriBot 部署与网络安全

MoriBot 面向个人部署，但可以安全地开放在公网。推荐原则只有一条：**只暴露一个 HTTPS 入口，MoriBot 本身监听回环地址，由反向代理或隧道终止 TLS。**

## 1. 三种推荐拓扑

### A. 云服务器 + Caddy/Nginx（最简单）

```text
手机 / 浏览器
      │ HTTPS / WSS (443)
      ▼
  Caddy / Nginx  ──► 127.0.0.1:6186  MoriBot
```

- 云厂商安全组只开放 `80/443`，关闭 `6186`。
- 反向代理自动申请 Let's Encrypt 证书。
- WebSocket 需要开启 Upgrade 转发（见下方示例）。

### B. 家里的电脑 + Cloudflare Tunnel / Tailscale Funnel

```text
手机 ──HTTPS/WSS──►  Cloudflare / Tailscale 边缘
                          │ 加密隧道（出站）
                          ▼
                    家中电脑 MoriBot
```

- 家庭网络**不需要**公网 IP、端口映射或 DDNS。
- 隧道由家中电脑主动向外建立，因此 CGNAT 环境也可用。
- 在隧道面板把域名转发到 `http://127.0.0.1:6186`。

### C. 家里的电脑 + 直接端口映射（不推荐，但可行）

- 只映射 `443`，不要映射 `6186`。
- 必须有有效证书（Let's Encrypt DNS-01 或可信的商业证书）。
- 配合 `force_https`、`trusted_hosts` 和防火墙白名单。
- 家庭宽带的公网 IP 变化时使用 DDNS。

## 2. 反向代理示例

### Caddy

```caddyfile
mori.example.com {
    reverse_proxy 127.0.0.1:6186
}
```

Caddy 会自动处理 TLS、`X-Forwarded-*` 和 WebSocket。

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name mori.example.com;

    ssl_certificate     /etc/letsencrypt/live/mori.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mori.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:6186;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

`/api/v1/mobile/ws` 是 WebSocket；没有 Upgrade 头会导致 MoriMobile 反复重连。

### Cloudflare Tunnel

```yaml
tunnel: moribot
credentials-file: /etc/cloudflared/<tunnel-id>.json

ingress:
  - hostname: mori.example.com
    service: http://127.0.0.1:6186
  - service: http_status:404
```

## 3. MoriBot 配置

```json
{
  "dashboard": {
    "host": "127.0.0.1",
    "port": 6186,
    "public_url": "https://mori.example.com",
    "trusted_hosts": ["mori.example.com"],
    "force_https": true,
    "proxy_headers": true,
    "forwarded_allow_ips": "127.0.0.1",
    "cors_origins": ["https://mori.example.com"],
    "ssl_certfile": "",
    "ssl_keyfile": ""
  }
}
```

说明：

| 配置 | 作用 |
| --- | --- |
| `public_url` | MoriMobile 配对链接中的公网地址；必须与手机实际访问的地址一致 |
| `trusted_hosts` | 只接受指定 Host 头，防止 Host 注入；反向代理后建议设置 |
| `force_https` | 将 HTTP 308 重定向到 HTTPS；必须确认代理会传 `X-Forwarded-Proto` |
| `forwarded_allow_ips` | 只信任这些来源的 `X-Forwarded-*`；默认本机代理 |
| `ssl_certfile` / `ssl_keyfile` | 直接由 Uvicorn 终止 TLS；通常留空，让代理处理 |

命令行也可以覆盖：

```bash
uv run main.py \
  --host 127.0.0.1 \
  --ssl-certfile /path/fullchain.pem \
  --ssl-keyfile /path/privkey.pem \
  --forwarded-allow-ips 127.0.0.1
```

> 只有反向代理和 MoriBot 在同一台机器时，`forwarded_allow_ips=127.0.0.1` 才安全。若代理在 Docker 网桥或另一台机器，请填写代理的真实出口地址，不能使用 `*`。

## 4. 已实现的安全措施

- **密码**：PBKDF2-HMAC-SHA256，600,000 次迭代 + 随机盐。
- **JWT**：随机密钥、过期时间、`token_version` 撤销机制；改密后旧令牌立即失效。
- **登录限流**：按客户端 IP 统计失败次数。
- **MoriMobile 设备令牌**：高熵随机令牌，数据库只存 SHA-256 哈希；支持单设备撤销、强制下线。
- **双认证平面**：后台 JWT 用于管理接口，设备令牌用于 `/api/v1/mobile/app/*` 和 WSS；两者不能互相替代。
- **配对码**：10 分钟有效、一次性、失败限流；生成配对码需要已登录后台。
- **安全响应头**：`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy`；HTTPS 下增加 HSTS。
- **CORS**：只允许配置中列出的来源。
- **WebSocket Origin 校验**：浏览器来源必须匹配 `cors_origins`、`public_url` 或当前 Host；原生客户端可无 Origin。
- **数据备份**：ZIP 完整性校验 + SQLite 在线快照；迁移文件包含密码哈希和 JWT 密钥，必须按机密文件保管。

## 5. MoriMobile 网络方向

MoriBot 只与官方手机客户端 [MoriMobile](https://github.com/an-shi/MoriMobile) 配套，不计划接入 QQ、Telegram、Discord 等第三方 IM。手机端的角色卡与对话生成走 HTTPS JSON API，服务端事件和推送走 WSS：

```text
MoriMobile ── HTTPS JSON ──► MoriBot /api/v1/mobile/app/*   角色卡/对话/设置
MoriMobile ── HTTPS 配对  ──► MoriBot /api/v1/mobile/pair    设备令牌
MoriMobile ── 出站 WSS    ──► MoriBot /api/v1/mobile/ws      事件/推送
```

反向代理需要同时正确转发普通 HTTPS 请求和 WebSocket Upgrade；只配置普通 `proxy_pass` 会导致 `/api/v1/mobile/ws` 无法建立。

手机主动连接服务器，而不是服务器主动连接手机，因此：

- 手机可以在任意运营商网络、Wi-Fi、漫游网络下使用。
- 家庭服务器不需要知道手机 IP，也不需要开放入站端口（有隧道时）。
- 服务器通过同一条连接回复消息。

配对流程：

1. 已登录后台的用户点击「连接 MoriMobile」，生成一次性配对码。
2. 手机 App 调用 `POST /api/v1/mobile/pair`（HTTPS）提交配对码和设备名。
3. 服务端返回设备令牌，手机安全保存（Keychain / Keystore）。
4. 手机用 `Authorization: Bearer <device_token>` 连接 `/api/v1/mobile/ws`。
5. 设备可在后台随时撤销，撤销后 WebSocket 立即收到 `revoked` 并被关闭。

详细协议见 [docs/morimobile.md](morimobile.md)。

## 6. 安全检查清单

- [ ] MoriBot 监听 `127.0.0.1`，公网只开 `443`
- [ ] 使用有效 TLS 证书，禁止生产环境裸 HTTP
- [ ] 设置 `public_url`、`trusted_hosts`、`force_https`
- [ ] 修改初始管理员密码，确认 `data/initial_admin.txt` 已删除
- [ ] 不把 `data/`、备份 ZIP、`.env` 提交到 Git 或公开网盘
- [ ] 定期导出备份，并在一台干净机器上验证可导入
- [ ] 不使用弱密码；不要复用其他网站密码
- [ ] 移除不再使用的 MoriMobile 设备
- [ ] 关注依赖更新与安全公告
- [ ] 如果使用隧道，限制隧道控制台的账号权限并开启 2FA

## 7. 为什么没有直接做端到端加密

MoriMobile 与 MoriBot 之间的传输由 TLS/WSS 保护，这已经防止了链路上的窃听和篡改。端到端加密（E2EE）需要额外的密钥协商、设备密钥备份和多端同步设计，对个人单用户场景收益有限，因此当前版本优先保证：**正确的 TLS、强令牌、可撤销设备和最小暴露面**。

如果未来需要跨不可信中继传输敏感消息，可以在 WebSocket 协议层增加基于 X25519 + AES-GCM 的会话加密，而不改变现有消息路由。
