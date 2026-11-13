# MoriBot

MoriBot 是一个受 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 架构启发的 **AI 助手后台控制器**，并与官方手机端 [MoriMobile](https://github.com/an-shi/MoriAI-mobile) 配套使用。它把「模型服务 / 消息管道 / 插件扩展 / MoriMobile 通信」拆成清晰的模块，用一个统一的 Web 控制台管理智能体。

MoriBot 的产品目标不是做多平台聊天机器人网关，**不计划接入 QQ、Telegram、Discord 等第三方 IM**。手机端只支持 MoriMobile。

当前版本是基础架构版本（v0.1.0），已经包含：

- 可扩展的核心生命周期与依赖装配
- 异步事件总线 + 洋葱模型消息管道
- 以 [MoriMobile](https://github.com/an-shi/MoriAI-mobile) 为唯一官方手机客户端
- 内建 MoriMobile 安全网关：设备配对、设备令牌、WebSocket 上下行、设备撤销
- MoriMobile 业务接口走 HTTPS JSON API，实时聊天走加密 WSS
- 三类模型配置：主模型 / 语音模型 / 图片模型
- 兼容主流供应商：OpenAI、DeepSeek、通义千问、Kimi、智谱 GLM、豆包、SiliconFlow、OpenRouter、Groq、Mistral、xAI、Ollama 等 OpenAI 兼容端点
- 原生适配 Anthropic Claude、Google Gemini、Azure OpenAI、ElevenLabs、MiniMax
- 主模型通过工具调用语音与图片模型，在对话中生成语音和图片
- 每日模型可用性定时检测，首页显示各模型最近状态
- SQLite 数据库与管理员账户
- JWT 登录、密码哈希、登录限流、反向代理/TLS 支持
- 一键数据导出 / 导入，运行数据可整体迁移
- 中文 / English 国际化，默认中文
- 登录页面与控制台首页（运行概览、模型可用性）

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
│   │   ├── platform/           # 内部平台抽象、MoriMobile 网关
│   │   ├── provider/           # 三类模型 Provider、OpenAI 兼容实现、工具网关
│   │   ├── plugin/             # 插件基类与文件系统加载器
│   │   ├── backup.py           # 可验证的数据导出/导入
│   │   ├── i18n.py             # 后端中英文消息
│   │   ├── security/           # 密码哈希、JWT、API Key 加密
│   │   └── logging.py          # 日志配置与 LogBroker
│   └── dashboard/
│       ├── app.py              # FastAPI 工厂、异常处理、SPA 托管
│       ├── deps.py             # 鉴权依赖
│       ├── routes/             # auth / system / mobile / providers
│       ├── services/           # 认证、MoriMobile 配对、模型配置
│       └── schemas.py          # Pydantic 请求/响应模型
├── dashboard/                  # Web 控制台
│   ├── src/i18n/               # 中文 / English 文案
│   ├── src/views/auth/LoginPage.vue
│   ├── src/views/HomePage.vue
│   ├── src/views/ProvidersPage.vue
│   ├── src/components/MobilePairingDialog.vue
│   ├── src/components/ProviderDialog.vue
│   ├── src/layouts/DefaultLayout.vue
│   └── ...
├── docs/
│   ├── architecture.md
│   ├── models.md               # 三类模型配置与工具调用
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

MoriMobile 官方仓库：[an-shi/MoriAI-mobile](https://github.com/an-shi/MoriAI-mobile)

1. 登录后台，点击首页右上角「连接 MoriMobile」。
2. 点击「生成配对码」，得到 8 位配对码和 `morimobile://` 配对链接。
3. 在手机 MoriMobile 中输入配对码，手机会获得一次性下发的设备令牌。
4. 手机通过 `WSS /api/v1/mobile/ws` 主动连接 MoriBot。

手机连接是**出站连接**，所以家庭服务器不需要知道手机 IP。公网部署、TLS、反向代理和隧道方案见 [docs/deployment.md](docs/deployment.md)，协议细节见 [docs/morimobile.md](docs/morimobile.md)。

> 公网使用前至少设置 `dashboard.public_url`、`trusted_hosts`、`force_https`，并确保只通过 HTTPS 暴露控制台。

### 5. 配置模型

登录后进入左侧「模型服务」，分别配置三类模型：

| 类型 | 职责 | 示例模型 |
| --- | --- | --- |
| 主模型 | 对话、推理、调用工具 | `gpt-4.1-mini` |
| 语音模型 | 把文本合成为语音 | `tts-1` |
| 图片模型 | 根据提示词生成图片 | `gpt-image-1` |

所有配置使用 OpenAI 兼容接口或原生适配器。界面提供供应商预设，选择 OpenAI、DeepSeek、通义千问、Kimi、GLM、豆包、Gemini、Claude、Azure、ElevenLabs、MiniMax、Groq、Together、SiliconFlow、DeepInfra 等预设会自动填充接口地址和参数默认值；也可以选择「自定义 / OpenAI 兼容」手动填写。MiniMax 国际账号选择 `api.minimax.io`，国内账号选择 `api.minimax.cn`，API Key 不能混用。API Key 使用安装密钥派生的 Fernet 加密存储，接口不会返回明文。

模型名称通过供应商官方接口动态获取：填好 Base URL 和 API Key 后，点击模型输入框右侧的刷新按钮即可下拉选择，不再依赖代码里的固定列表。获取时还会记录模型能力（图片识别、工具调用、推理、上下文窗口），保存后显示在配置卡片上，对话层据此决定是否发送图片或工具。主模型还提供「平衡 / 精确 / 创意」参数预设，手动修改后自动切换为自定义。

主模型会通过 `generate_speech` 和 `generate_image` 两个工具调用默认语音/图片模型；实现位于 `moribot/core/provider/gateway.py`，后续对话服务直接消费 `ModelGateway.chat()` 即可。详细说明见 [docs/models.md](docs/models.md)。

### 6. 数据迁移

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
    "default_chat_provider_id": "",
    "media_model_fallbacks": {
      "minimax": {
        "speech": ["speech-2.8-turbo", "speech-2.8-hd"],
        "image": ["MiniMax-H3-Image", "MiniMax-H3-Image-Highspeed"]
      }
    },
    "retired_model_prefixes": {
      "minimax": ["minimax-m2"]
    },
    "health_check": {
      "enabled": false,
      "times": ["09:00"],
      "last_runs": {}
    }
  },
  "platform": {},
  "mobile": {
    "max_devices": 10,
    "pairing_code_ttl_minutes": 10
  }
}
```

`provider.media_model_fallbacks` 用于 MiniMax 这类 `/models` 不返回语音/图片模型的供应商；`provider.retired_model_prefixes` 用于隐藏接口仍返回但已下线的模型。后续模型更新时直接修改这两个配置并重启即可，不需要改代码。

`provider.health_check` 控制系统设置页的模型定时检测。`times` 支持多个 `HH:MM`，使用服务器本地时间；检测结果会写回模型配置并显示在首页。

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
| GET | `/api/v1/system/settings` | 是 | 读取系统设置（模型定时检测） |
| PATCH | `/api/v1/system/settings` | 是 | 保存模型定时检测开关与时间 |
| POST | `/api/v1/system/model-health/run` | 是 | 立即检测所有已启用模型 |
| GET | `/api/v1/system/backup/export` | 是 | 下载完整数据备份 |
| GET | `/api/v1/providers` | 是 | 列出三类模型配置 |
| GET | `/api/v1/providers/catalog` | 是 | 获取支持的适配器与供应商预设 |
| POST | `/api/v1/providers/models` | 是 | 从供应商官方接口获取模型列表与能力 |
| POST | `/api/v1/providers` | 是 | 创建模型配置 |
| PATCH | `/api/v1/providers/{id}` | 是 | 更新模型配置（API Key 留空保持） |
| DELETE | `/api/v1/providers/{id}` | 是 | 删除模型配置 |
| POST | `/api/v1/providers/{id}/default` | 是 | 设置该类型默认模型 |
| POST | `/api/v1/providers/{id}/test` | 是 | 发起一次真实连通性测试 |
| POST | `/api/v1/mobile/pairing-code` | 是 | 生成一次性 MoriMobile 配对码 |
| POST | `/api/v1/mobile/pair` | 否（配对码） | 手机兑换设备令牌 |
| GET | `/api/v1/mobile/app/me` | 设备令牌 | 校验设备并返回设备/账户信息 |
| GET | `/api/v1/mobile/devices` | 是 | 已配对设备 |
| POST | `/api/v1/mobile/devices/{id}/message` | 是 | 从控制台向在线设备发送消息 |
| POST | `/api/v1/mobile/devices/{id}/revoke` | 是 | 撤销设备并强制下线 |
| WS | `/api/v1/mobile/ws` | 设备令牌 | MoriMobile 双向消息通道 |

受保护接口使用请求头：

```http
Authorization: Bearer <access_token>
```

MoriMobile 的设备令牌通过 `Authorization: Bearer <device_token>` 或 `X-Mori-Device-Token` 传递。

### HTTP 与 WSS 的分工

MoriMobile 使用两条独立通道：

| 通道 | 用途 | 认证 |
| --- | --- | --- |
| HTTPS JSON API | 配对、设备信息、后续的会话列表、历史记录、模型设置、文件上传等常规业务 | 设备令牌（`/mobile/app/*`）或后台 JWT（管理接口） |
| WSS `/api/v1/mobile/ws` | 实时聊天、流式回复、服务端推送、心跳、ACK | 设备令牌 |

底层 `EventBus`、`Pipeline` 和业务 Service 不依赖传输方式。新增业务能力时优先加 HTTP 接口；只有需要实时推送或流式传输时才走 WSS，不要把 CRUD 请求塞进 WebSocket。

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

### 新增 MoriMobile HTTP 业务接口

MoriMobile 的常规业务接口应放在 `/api/v1/mobile/app/*` 下，并依赖设备认证上下文：

```python
from fastapi import APIRouter, Depends

from moribot.dashboard.deps import MobileAuthContext, get_mobile_auth_context

router = APIRouter(prefix="/mobile/app", tags=["mobile-app"])


@router.get("/conversations")
async def list_conversations(
    auth: MobileAuthContext = Depends(get_mobile_auth_context),
):
    # auth.device 是当前设备，auth.user 是设备绑定的账户
    ...
```

后台管理接口继续使用 `get_current_user`（JWT），手机端业务接口使用 `get_mobile_auth_context`（设备令牌），两种认证不会混用。只有实时聊天、流式输出和推送才使用 WSS。

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
- [ ] 主模型流式输出、重试与多轮 Agent 工具调用完善
- [ ] MoriMobile 业务 API 与多端同步
- [ ] 插件管理页与插件市场
- [ ] 实时日志控制台
- [ ] 可视化配置编辑与模型连通性测试
- [ ] MoriMobile 离线消息队列与推送通知

## License

[MIT](LICENSE)
