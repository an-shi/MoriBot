# MoriBot

MoriBot 是一个受 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 架构启发的 **AI 助手后台控制器**。它把「平台接入 / 模型服务 / 消息管道 / 插件扩展」拆成清晰的模块，用一个统一的 Web 控制台管理智能体。

当前版本是基础架构版本（v0.1.0），已经包含：

- 可扩展的核心生命周期与依赖装配
- 异步事件总线 + 洋葱模型消息管道
- 平台适配器、模型提供方、插件系统的抽象层
- 内建 MoriMobile 安全网关：设备配对、设备令牌、WebSocket 上下行、设备撤销
- SQLite 数据库与管理员账户
- JWT 登录、密码哈希、登录限流、反向代理/TLS 支持
- 一键数据导出 / 导入，运行数据可整体迁移
- 中文 / English 国际化，默认中文
- 登录页面与空白工作台首页（Vue 3 + Vuetify 3）

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.11+ / FastAPI / Uvicorn |
| 数据 | SQLAlchemy Async / SQLModel / SQLite |
| 配置 | JSON 配置文件 + `.env` 环境变量 |
| 日志 | Loguru（控制台 + 滚动文件 + 内存日志 Broker） |
| 鉴权 | JWT（HS256）+ PBKDF2-SHA256 密码哈希 |
| 手机端 | MoriMobile：出站 WSS + 一次性配对码 + 可撤销设备令牌 |
| 迁移 | 自描述 ZIP + SHA-256 校验 + SQLite 在线快照 |
| 前端 | Vue 3 / Vite / TypeScript / Pinia / Vue Router / Vuetify 3 / vue-i18n |

## 目录结构

```text
MoriBot/
├── main.py                     # uv run main.py 的入口
├── moribot/
│   ├── cli.py                  # 命令行参数、备份命令与 Uvicorn 启动
│   ├── core/
│   │   ├── lifecycle.py        # 核心生命周期：初始化、启动、停止
│   │   ├── context.py          # 暴露给插件的运行时上下文
│   │   ├── accounts.py         # 首次启动的管理员账户
│   │   ├── config/             # 配置默认值与 JSON 管理器
│   │   ├── db/                 # 数据库接口、模型与 SQLite 实现
│   │   ├── event/              # 归一化事件模型与异步事件总线
│   │   ├── pipeline/           # Stage 基类、注册表与调度器
│   │   ├── platform/           # 平台适配器抽象、MoriMobile 网关
│   │   ├── provider/           # 模型提供方抽象与管理器
│   │   ├── plugin/             # 插件基类与文件系统加载器
│   │   ├── backup.py           # 可验证的数据导出/导入
│   │   ├── i18n.py             # 后端中英文消息
│   │   ├── security/           # 密码哈希与 JWT
│   │   └── logging.py          # 日志配置与 LogBroker
│   └── dashboard/
│       ├── app.py              # FastAPI 工厂、异常处理、SPA 托管
│       ├── deps.py             # 鉴权依赖
│       ├── routes/             # auth / system / mobile
│       ├── services/           # 认证、MoriMobile 配对
│       └── schemas.py          # Pydantic 请求/响应模型
├── dashboard/                  # Web 控制台
│   ├── src/i18n/               # 中文 / English 文案
│   ├── src/views/auth/LoginPage.vue
│   ├── src/views/HomePage.vue
│   ├── src/components/MobilePairingDialog.vue
│   ├── src/layouts/DefaultLayout.vue
│   └── ...
├── docs/
│   ├── architecture.md
│   ├── deployment.md           # 公网部署与网络安全
│   ├── morimobile.md           # 手机端配对与 WebSocket 协议
│   └── data-migration.md       # 数据迁移与备份
└── tests/                      # 后端测试
```

更完整的架构说明见 [docs/architecture.md](docs/architecture.md)。

## 快速开始

### 1. 启动后端

```bash
uv sync
uv run main.py
```

首次启动会自动完成：

1. 创建 `data/config.json`（包含随机 JWT 密钥）
2. 创建 `data/moribot.db`
3. 生成管理员账户 `admin` 和随机强密码
4. 在启动日志中打印账号密码，同时写入 `data/initial_admin.txt`

默认地址：`http://127.0.0.1:6186`  
API 文档：`http://127.0.0.1:6186/api/docs`

忘记密码时：

```bash
uv run main.py --reset-password
```

### 2. 启动前端开发服务器

```bash
cd dashboard
pnpm install
pnpm dev
```

打开 `http://localhost:5173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:6186`。

### 3. 构建前端并由后端托管

```bash
cd dashboard
pnpm build
```

构建产物位于 `dashboard/dist`。重新启动后端后，访问 `http://127.0.0.1:6186` 即可看到控制台。

### 4. 连接 MoriMobile

1. 登录后台，点击首页右上角「连接 MoriMobile」。
2. 点击「生成配对码」，得到 8 位配对码和 `morimobile://` 配对链接。
3. 在手机 MoriMobile 中输入配对码，手机会获得一次性下发的设备令牌。
4. 手机通过 `WSS /api/v1/mobile/ws` 主动连接 MoriBot。

手机连接是**出站连接**，所以家庭服务器不需要知道手机 IP。公网部署、TLS、反向代理和隧道方案见 [docs/deployment.md](docs/deployment.md)，协议细节见 [docs/morimobile.md](docs/morimobile.md)。

> 公网使用前至少设置 `dashboard.public_url`、`trusted_hosts`、`force_https`，并确保只通过 HTTPS 暴露控制台。

### 5. 数据迁移

首页「导出数据」会下载一个包含配置、数据库、插件及未来所有运行数据的 ZIP。迁移到另一台机器：

```bash
# 旧机器
uv run moribot backup export -o moribot-backup.zip

# 新机器（先停止 MoriBot）
uv run moribot backup import moribot-backup.zip --yes
uv run main.py
```

导入前后会自动校验 SHA-256 和数据库完整性，并保留 `data.pre-import-<时间>` 作为回滚点。系统日志不迁移。完整说明见 [docs/data-migration.md](docs/data-migration.md)。

## 配置

默认配置写入 `data/config.json`：

```json
{
  "config_version": 1,
  "bot": {
    "name": "MoriBot",
    "description": "可扩展的 AI 助手后台控制器",
    "locale": "zh-CN",
    "log_level": "INFO"
  },
  "dashboard": {
    "host": "127.0.0.1",
    "port": 6186,
    "jwt_secret": "<启动时自动生成>",
    "token_expire_hours": 168,
    "public_url": "",
    "trusted_hosts": [],
    "force_https": false,
    "proxy_headers": true,
    "forwarded_allow_ips": "127.0.0.1",
    "ssl_certfile": "",
    "ssl_keyfile": "",
    "cors_origins": ["http://localhost:5173", "http://127.0.0.1:5173"]
  },
  "provider": {
    "default_chat_provider_id": ""
  },
  "platform": {},
  "mobile": {
    "max_devices": 10,
    "pairing_code_ttl_minutes": 10
  }
}
```

常用环境变量（可放在项目根目录的 `.env`）：

| 变量 | 说明 |
| --- | --- |
| `MORIBOT_DATA_DIR` | 数据目录，默认 `./data` |
| `MORIBOT_WEBUI_DIR` | 前端构建目录，默认自动寻找 `dashboard/dist` |
| `MORIBOT_HOST` | 监听地址 |
| `MORIBOT_PORT` | 监听端口 |
| `MORIBOT_LOG_LEVEL` | 日志级别 |
| `MORIBOT_FORWARDED_ALLOW_IPS` | 信任的反向代理地址 |
| `MORIBOT_LOCALE` | 备份命令行输出的语言（`zh-CN` / `en-US`） |

命令行参数优先级最高：

```bash
uv run main.py --host 127.0.0.1 --port 8080 --data-dir ./my-data
```

公网/反向代理配置见 [docs/deployment.md](docs/deployment.md)。

## API

所有接口返回统一信封：

```json
{
  "status": "ok",
  "message": "登录成功",
  "data": {}
}
```

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/system/public` | 否 | 登录页所需的名称与版本 |
| GET | `/api/v1/system/health` | 否 | 存活探针 |
| POST | `/api/v1/auth/login` | 否 | 用户名密码换取 JWT |
| GET | `/api/v1/auth/me` | 是 | 当前账户 |
| POST | `/api/v1/auth/change-password` | 是 | 修改密码并刷新令牌 |
| POST | `/api/v1/auth/logout` | 是 | 登出确认（客户端丢弃令牌） |
| GET | `/api/v1/system/info` | 是 | 首页运行状态 |
| GET | `/api/v1/system/backup/export` | 是 | 下载完整数据备份 |
| POST | `/api/v1/mobile/pairing-code` | 是 | 生成一次性 MoriMobile 配对码 |
| POST | `/api/v1/mobile/pair` | 否（配对码） | 手机兑换设备令牌 |
| GET | `/api/v1/mobile/devices` | 是 | 已配对设备 |
| POST | `/api/v1/mobile/devices/{id}/message` | 是 | 从控制台向在线设备发送消息 |
| POST | `/api/v1/mobile/devices/{id}/revoke` | 是 | 撤销设备并强制下线 |
| WS | `/api/v1/mobile/ws` | 设备令牌 | MoriMobile 双向消息通道 |

受保护接口使用请求头：

```http
Authorization: Bearer <access_token>
```

MoriMobile 的设备令牌通过 `Authorization: Bearer <device_token>` 或 `X-Mori-Device-Token` 传递。

## 国际化

- 前端默认中文，可在登录页和控制台右上角切换 English。
- 语言选择保存在浏览器 `localStorage`，并通过 `Accept-Language` 传给后端。
- 后端错误消息按 `Accept-Language` / `X-Mori-Locale` 返回中文或英文。
- 修改默认语言：`data/config.json` → `bot.locale`（`zh-CN` 或 `en-US`）。

## 扩展点

### 新增消息管道阶段

```python
from moribot.core.pipeline import Stage, register_stage


@register_stage
class MyStage(Stage):
    async def initialize(self, ctx):
        self.ctx = ctx

    async def process(self, event):
        # 返回 None 继续执行后续阶段；返回异步生成器可做洋葱式后置处理
        if event.message == "ping":
            event.extras["reply"] = "pong"
            event.stop()
```

### 新增模型提供方

继承 `moribot.core.provider.Provider`，实现 `chat()`，然后注册到 `ProviderManager`：

```python
from moribot.core.provider import ChatMessage, Provider, ProviderResponse


class EchoProvider(Provider):
    provider_type = "echo"

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ProviderResponse:
        return ProviderResponse(text=messages[-1].content)


core.provider_manager.register(EchoProvider("echo-1", model="echo"))
```

### 新增平台适配器

继承 `moribot.core.platform.PlatformAdapter`，实现 `start()`、`stop()` 与 `send_message()`，把平台消息转换为 `MoriEvent` 后投递到 `event_bus`，再注册到 `PlatformManager`。

### 编写插件

在 `data/plugins/<name>/plugin.py` 中：

```python
from moribot.core.plugin import MoriPlugin


class Plugin(MoriPlugin):
    name = "hello"
    version = "0.1.0"
    description = "Example plugin"

    async def initialize(self, ctx):
        self.ctx = ctx


plugin = Plugin()
```

插件可以访问 `ctx.config`、`ctx.db`、`ctx.event_bus`、`ctx.provider_manager` 和 `ctx.platform_manager`。

## 开发

```bash
uv sync
uv run ruff check .
uv run pytest
```

前端：

```bash
cd dashboard
pnpm install
pnpm typecheck
pnpm build
```

## 路线图

已完成：

- [x] MoriMobile 配对、设备令牌、WebSocket 网关、设备撤销
- [x] 数据导出 / 导入与完整性校验
- [x] 中英文 i18n（默认中文）
- [x] 公网部署的 TLS / 反向代理 / 安全头基线

后续：

- [ ] 会话与消息历史
- [ ] OpenAI / Anthropic / Gemini 等模型提供方
- [ ] QQ、Telegram、Discord、WebChat 等平台适配器
- [ ] 插件管理页与插件市场
- [ ] 实时日志控制台
- [ ] 可视化配置编辑与模型连通性测试
- [ ] MoriMobile 离线消息队列与推送通知

## License

[MIT](LICENSE)
