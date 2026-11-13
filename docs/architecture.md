# MoriBot 架构说明

本文描述 MoriBot v0.1.0 的基础架构。MoriBot 是 [MoriMobile](https://github.com/an-shi/MoriMobile) 的配套后台，产品范围不包含 QQ、Telegram、Discord 等第三方 IM 接入。设计目标不是复刻 AstrBot 的全部功能，而是借鉴它「核心生命周期 + 事件总线 + 管道 + 模型抽象 + 插件」的分层方式，先建立一个可以持续生长的骨架。

## 1. 设计原则

- **模块边界清晰**：MoriMobile 网关、模型、消息管道、插件、Web 控制台各自独立。
- **异步优先**：消息接收、模型调用、日志分发都基于 `asyncio`，慢操作不阻塞手机连接。
- **接口先于实现**：`Provider`、`PlatformAdapter`、`Stage`、`MoriPlugin` 都是内部抽象层；平台层只为 MoriMobile 服务，不作为第三方 IM 扩展点。
- **默认安全**：首次启动生成随机管理员密码；密码使用 PBKDF2-SHA256 加盐存储；JWT 密钥随机生成并持久化；登录失败有限流。
- **KISS**：当前只保留真正被使用的代码，不提前引入向量数据库、工作流引擎或复杂插件市场。

## 2. 分层视图

```text
┌─────────────────────────────────────────────────────────────┐
│                        Vue 3 Dashboard                      │
│  LoginPage / DefaultLayout / HomePage / Pinia / Router      │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS /api/v1/* (JWT)
┌───────────────────────────▼─────────────────────────────────┐
│                     FastAPI Dashboard                       │
│  routes/auth  routes/system  routes/mobile  services/deps   │
│  管理 API + MoriMobile HTTPS API + WSS 网关                 │
│  静态 SPA 托管 + 统一响应信封 + 异常处理 + 登录限流           │
└───────────────────────────┬─────────────────────────────────┘
                            │ app.state.core
┌───────────────────────────▼─────────────────────────────────┐
│                      CoreLifecycle                          │
│  装配数据库、管理器、管道、事件总线、插件，并管理启动/停止顺序  │
└──────┬──────────────┬──────────────┬──────────────┬─────────┘
       │              │              │              │
┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐
│ EventBus   │ │  Pipeline  │ │  Providers │ │ MoriMobile  │
│ asyncio    │ │ Stage 1..N │ │  registry  │ │  adapter    │
│ queue      │ │ onion model│ │            │ │             │
└──────┬─────┘ └──────┬─────┘ └────────────┘ └──────┬──────┘
       │              │                              │
       └──────────────┴──────────────┬───────────────┘
                                     │
                       ┌─────────────▼─────────────┐
                       │ SQLite + Config + LogBroker│
                       └───────────────────────────┘
```

## 3. 目录职责

| 路径 | 职责 |
| --- | --- |
| `moribot/core/lifecycle.py` | 组件装配、启动/停止顺序、运行状态 |
| `moribot/core/config/` | JSON 配置默认值、递归补全、原子写入、JWT 密钥生成 |
| `moribot/core/db/` | `BaseDatabase` 抽象、SQLModel 表、SQLite 实现 |
| `moribot/core/event/` | `MoriEvent` 归一化事件、异步事件总线 |
| `moribot/core/pipeline/` | `Stage` 契约、注册表、洋葱模型调度器、内置阶段 |
| `moribot/core/platform/` | 内部平台抽象、MoriMobile 网关适配器 |
| `moribot/core/provider/` | 三类模型 Provider、OpenAI 兼容实现、默认选择与工具调用网关 |
| `moribot/core/plugin/` | 插件基类、`PluginContext` 协议、文件系统加载器 |
| `moribot/core/accounts.py` | 首次启动管理员账户、密码重置、凭据文件 |
| `moribot/core/backup.py` | 自描述 ZIP 备份、校验、原子导入 |
| `moribot/core/i18n.py` | 后端中英文消息与语言协商 |
| `moribot/core/logging.py` | Loguru 控制台/文件 Sink、内存日志 Broker |
| `moribot/dashboard/app.py` | FastAPI 工厂、CORS、GZip、安全头、异常处理、SPA 托管 |
| `moribot/dashboard/routes/` | `/api/v1/auth`、`/system`、`/mobile`、`/providers`、`/characters` |
| `dashboard/src/` | Vue 控制台，登录页、工作台、MoriMobile 配对弹窗 |

## 4. 启动生命周期

`moribot.cli.main()` 的执行顺序：

1. 读取 `.env`，解析命令行参数。
2. 解析数据目录，创建 `data/`、`data/logs/`、`data/plugins/`。
3. 加载 `data/config.json`；缺失时写入默认值并生成 JWT 密钥。
4. 配置 Loguru（控制台、滚动文件、LogBroker）。
5. 如果传入 `--reset-password`，先独立打开数据库重置管理员密码。
6. 创建 FastAPI 应用与 `CoreLifecycle`。
7. Uvicorn 启动，进入 FastAPI lifespan：
   - `db.initialize()` 建表；
   - 首次启动时创建 `admin` 账户；
   - 初始化管道阶段；
   - 加载 `data/plugins/*/plugin.py`；
   - 启动事件总线；
   - 启动 MoriMobile 网关适配器；
   - 标记运行状态。
8. 关闭时按相反顺序停止总线、平台、插件、Provider 和数据库。

> 管理员密码只在首次创建或 `--reset-password` 时生成，并同时输出到日志与 `data/initial_admin.txt`。修改密码后凭据文件会自动删除。

## 5. HTTP 请求流程

以登录为例：

```text
LoginPage.vue
  └─ authStore.login()
       └─ POST /api/v1/auth/login
            ├─ LoginRateLimiter.retry_after(ip)
            ├─ AuthService.login(username, password)
            │    ├─ db.get_user_by_username()
            │    ├─ verify_password(pbkdf2)
            │    ├─ db.record_login()
            │    └─ create_access_token(HS256, sub/role/ver/exp)
            └─ { status: "ok", data: { access_token, user } }
```

前端把 token 存入 `localStorage`（勾选“保持登录”）或 `sessionStorage`，Axios 请求拦截器自动添加：

```http
Authorization: Bearer <token>
```

后端 `get_current_user` 统一校验签名、过期时间、账户状态和 `token_version`。修改密码会递增 `token_version`，使旧 token 立即失效。

### 5.1 两类认证主体

MoriBot 有意区分后台用户与手机设备：

| 调用方 | 认证方式 | 依赖 | 典型接口 |
| --- | --- | --- | --- |
| Web 控制台 | 管理员 JWT | `get_current_user` | 登录、系统信息、生成配对码、设备管理、数据导出 |
| MoriMobile | 设备令牌 | `get_mobile_auth_context` | `/api/v1/mobile/app/*` 角色卡、会话、消息、媒体、WSS |
| 未配对手机 | 一次性配对码 | 无（限流） | `POST /api/v1/mobile/pair` |

`/api/v1/mobile/app/me` 用于校验设备令牌并获取设备与账户信息；`/app/characters` 提供角色卡，`/app/conversations` 管理会话，`/app/conversations/{id}/messages` 读取历史并生成回复，`/app/media/{filename}` 下载生成媒体。后续模型设置、文件上传等接口统一放在 `/api/v1/mobile/app/*` 下，依赖 `MobileAuthContext`。后台 JWT 与设备令牌不能互相替代。

## 6. 消息事件流

MoriMobile 是唯一官方平台客户端，数据流已经固定：

```text
MoriMobile App
  └─ 出站 WSS /api/v1/mobile/ws + 设备令牌
       └─ MobilePlatformAdapter 注册连接
            └─ event_bus.put(MoriEvent)
                 └─ EventBus._consume()
                      └─ asyncio.create_task(PipelineScheduler.execute(event))
                           ├─ PreprocessStage   文本归一化
                           ├─ ProcessStage      调用 Provider / Agent（预留）
                           └─ RespondStage      通过 MobilePlatformAdapter 回复
```

- 每个事件独立 task，默认最多 16 个并发（`EventBus(max_concurrency=16)`）。
- 手机的正常对话由 `POST /api/v1/mobile/app/conversations/{id}/messages` 同步调用 `ModelGateway` 并写入会话表，不经过事件总线；事件总线保留给 WSS 事件和后续实时推送。
- `MoriEvent.stop()` 可以中止后续阶段。
- 阶段返回异步生成器时使用洋葱模型：`yield` 前的代码先执行，`yield` 后的代码在后续阶段全部完成后执行。
- 管道调度器在异步生成器分支结束后会直接返回，避免后续阶段被重复执行。
- 设备离线时当前版本丢弃下行消息；离线队列属于后续演进。

## 6.1 MoriMobile 安全网关

- 配对码由已登录后台生成，10 分钟有效、单次使用、服务端只存哈希。
- 手机用配对码换取高熵设备令牌，数据库只存 SHA-256。
- 手机主动出站连接 WebSocket，家庭服务器不需要连接手机或暴露额外端口。
- 角色卡和对话生成通过 HTTPS 设备令牌接口完成，不依赖 WebSocket 是否在线。
- 设备可撤销，撤销会立即向 WebSocket 发送 `revoked` 并以 4001 关闭。
- 浏览器 Origin 会校验；原生 App 可以不带 Origin，依靠设备令牌认证。
- 详细协议见 [morimobile.md](morimobile.md)。

## 6.2 HTTP 与 WSS 的边界

```text
MoriMobile
  ├─ HTTPS JSON API  ──►  /api/v1/mobile/app/*   角色卡、会话、消息、媒体、设置
  ├─ HTTPS 配对      ──►  /api/v1/mobile/pair     一次性设备令牌
  └─ WSS             ──►  /api/v1/mobile/ws      服务端事件、推送、连接状态
```

- **常规业务走 HTTPS**：CRUD、分页、文件上传下载、配置读取、对话生成等使用普通 JSON 接口，便于缓存、重试、错误码和网关日志。
- **WSS 只承载实时事件**：服务端推送、ACK、心跳和连接状态；对话请求不使用 WSS。
- **不把 CRUD 塞进 WebSocket**：否则会失去 HTTP 的幂等、缓存、鉴权和可观测性。
- **Service 层与传输无关**：`EventBus`、`Pipeline` 和业务 Service 不关心消息来自 WSS 还是一条 HTTP 请求；路由只负责协议转换。
- **认证分离**：管理接口用后台 JWT，手机业务接口用 `get_mobile_auth_context` 设备令牌。

## 6.3 模型角色与工具调用

模型配置分为三个固定角色：`chat`、`speech`、`image`。Provider 层负责协议适配，`ModelGateway` 负责编排：

```text
主模型 chat.completions(tools=[generate_speech, generate_image])
  ├─ tool_call generate_speech → 角色指定或默认语音模型 → SpeechResult
  ├─ tool_call generate_image  → 角色指定或默认图片模型 → GeneratedImage[]
  └─ 主模型收到 tool 结果 → 最终文本
```

- 只有配置了对应语音/图片模型，工具才会出现在主模型请求中。
- `ModelGateway` 支持传入角色卡的 `chat_provider_id` / `speech_provider_id` / `image_provider_id`；为空时回退该类别的系统默认模型。
- 工具调用结果和媒体附件通过 `ModelReply` 返回给上层对话服务。
- 模型配置中的 `capabilities` 记录输入/输出模态、工具与推理能力，来自供应商接口或名称推断，对话层据此决定是否接受图片、发送工具定义。
- API Key 使用安装密钥派生的 Fernet 加密存储，数据库读取不会直接暴露明文。
- 模型配置保存在 `model_providers` 表，随数据库备份迁移；旧库启动时自动补 `capabilities` 列。
- 角色卡保存在 `character_cards` 表，头像文件位于数据目录 `avatars/`，同样随备份迁移；角色卡可按类别覆盖模型，未覆盖时使用系统默认模型。
- 会话保存在 `conversations` 表，消息保存在 `conversation_messages` 表；用户消息和助手回复在同一个事务中写入。
- 生成的语音和图片保存在 `data/media/<user_id>/`，消息只保存媒体描述和受鉴权保护的 URL，避免把大段 base64 写进数据库。
- 模型上下文默认取会话最近 100 条消息，并限制总字符数；完整历史仍保留在数据库中。
- 删除会话会级联删除消息记录和该会话的本地媒体文件。
- 系统设置可开启每日模型可用性检测，按多个本地时间自动执行测试连接；结果写入 `last_test_*`，首页展示各模型状态。

## 6.4 数据可迁移性
所有运行数据都必须写入 `AppPaths.data_dir`。备份服务会：

1. 用 SQLite 在线备份 API 生成一致性数据库快照。
2. 收集 `data/` 下除日志、一次性凭据、临时目录外的全部文件。
3. 为每个文件计算 SHA-256 并写入 `manifest.json`。
4. 导入时校验路径安全、文件大小、哈希、配置 JSON 和 SQLite 完整性。
5. 原子替换数据目录，并保留 `data.pre-import-*` 回滚点。

未来新增的模型配置、会话消息、模型记忆、上传文件只要落在数据目录，就会自动进入备份，无需修改迁移代码。MoriMobile 的本地缓存不属于迁移范围，换机后从服务端重新同步即可。详见 [data-migration.md](data-migration.md)。

## 7. 扩展点

### 7.1 新增 MoriMobile HTTP 业务接口

MoriMobile 的常规业务接口放在 `/api/v1/mobile/app/*` 下，依赖设备认证上下文：

```python
from fastapi import APIRouter, Depends

from moribot.dashboard.deps import MobileAuthContext, get_mobile_auth_context

router = APIRouter(prefix="/mobile/app", tags=["mobile-app"])


@router.get("/characters")
async def list_characters(
    auth: MobileAuthContext = Depends(get_mobile_auth_context),
):
    # auth.device 是当前设备，auth.user 是设备绑定的账户
    ...
```

这是产品范围内唯一的手机接入方式。MoriBot 不计划新增 QQ、Telegram、Discord 等平台适配器。

### 7.2 新增模型提供方

实现 `Provider.chat()`，然后：

```python
self.provider_manager.register(MyProvider("openai-1", model="gpt-4o-mini"), default=True)
```

`ModelGateway` 可以通过 `chat_provider_id` / `speech_provider_id` / `image_provider_id` 使用角色卡指定的 Provider；未指定时回退该类别的默认提供方。`ProcessStage` 目前仍是占位实现，移动端消息由 `/api/v1/mobile/app/conversations/{id}/messages` 直接调用 `ModelGateway` 并持久化结果。

### 7.3 新增管道阶段

```python
@register_stage
class RateLimitStage(Stage):
    async def initialize(self, ctx):
        self.ctx = ctx

    async def process(self, event):
        if too_many(event):
            event.stop()
```

`STAGE_ORDER` 控制内置阶段的顺序；未列出的阶段会追加到末尾。

### 7.4 插件

插件是 `data/plugins/<name>/plugin.py`，暴露一个 `plugin` 实例或 `Plugin` 类。插件可以访问：

- `ctx.config`：运行时配置
- `ctx.db`：数据库
- `ctx.event_bus`：事件总线
- `ctx.provider_manager`：模型提供方
- `ctx.platform_manager`：内部平台管理器（当前仅 MoriMobile）

插件通过 `PluginContext` Protocol 与核心解耦，可以独立测试。

## 8. 数据与配置

| 文件 | 说明 |
| --- | --- |
| `data/config.json` | 运行时配置，启动时自动补全缺失字段 |
| `data/moribot.db` | SQLite 数据库（WAL 模式，含账户、MoriMobile 设备、模型配置） |
| `data/logs/moribot.log` | 滚动日志（10 MB × 14 天） |
| `data/initial_admin.txt` | 一次性初始凭据，修改密码后删除 |
| `data/plugins/` | 插件目录 |

配置采用「默认值 + 用户覆盖」的递归合并方式。新增配置项只需要修改 `DEFAULT_CONFIG`，已有用户的配置文件会在下次启动时自动补全。

## 9. 安全设计

- **密码**：PBKDF2-HMAC-SHA256，600,000 次迭代，16 字节随机盐，常量时间比较。
- **JWT**：HS256，包含 `iss/sub/role/ver/iat/exp/jti`；密钥首次启动生成并写入配置。
- **令牌撤销**：账户上的 `token_version` 在密码变更时 +1，旧 token 立即失效。
- **登录限流**：按客户端 IP 统计失败次数，5 次/60 秒后锁定 120 秒。
- **初始凭据**：仅在首次启动/重置时打印；修改密码后删除明文文件。
- **MoriMobile**：一次性配对码 + 哈希设备令牌 + 设备撤销 + Origin 校验 + 消息大小限制。
- **双认证平面**：后台 JWT 与手机设备令牌分离；设备业务接口通过 `MobileAuthContext` 校验，不能使用后台令牌冒充设备。
- **网络**：CORS 白名单、可选可信 Host、可选 HTTPS 强制跳转、HSTS（HTTPS 下）、代理头白名单。
- **备份**：SHA-256 完整性校验、Zip Slip 防护、SQLite integrity_check、原子替换和回滚目录。
- **模型密钥**：API Key 使用安装密钥派生的 Fernet 加密存储；接口只返回是否已设置和末尾提示。
- **响应信封**：错误不会泄漏堆栈；未捕获异常统一记录日志并返回 500。
- **i18n**：错误消息通过 `Accept-Language` / `X-Mori-Locale` 本地化，默认中文。

## 10. 与 AstrBot 的差异

| 维度 | AstrBot | MoriBot（当前） |
| --- | --- | --- |
| 平台 | 十多个内建平台适配器 | 仅配套 MoriMobile；不计划第三方 IM |
| 模型 | 多厂商 Provider + Agent Runner | 三类模型、主流供应商预设、原生 Claude/Gemini/Azure/ElevenLabs/MiniMax 适配 |
| 插件 | 完整的 Star 插件体系、市场、权限 | 文件系统插件加载 + 上下文协议 |
| 消息管道 | 多阶段、限流、白名单、内容安全等 | 预处理 / 处理 / 响应三阶段占位 |
| 数据库 | 大量业务表与迁移 | 用户、MoriMobile 设备、模型配置表 + 通用数据库接口 |
| WebUI | Vuetify 大型控制台 | 登录页、空白工作台、MoriMobile 配对与数据导出 |
| 数据迁移 | 备份功能 | 自描述 ZIP + 完整性校验 + 原子导入 |

这些差异是刻意保留的：先把边界和生命周期定稳，再按实际需求逐个填充能力，避免在基础阶段背负过多实现细节。

## 11. 后续演进

1. 消息重生成、消息删除、会话归档与流式输出。
2. 主模型自动重试和多轮 Agent 工具调用完善。
3. MoriMobile 业务 API（模型设置、文件上传）。
4. 插件管理 API 与热重载。
5. SSE 实时日志（复用 `LogBroker`）。
6. 前端登录后的账户安全页与系统设置页。
7. MoriMobile 离线消息队列、推送通知和设备级消息历史。
8. 备份口令加密与定时自动备份。