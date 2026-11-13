# 模型配置与工具调用

MoriBot 把模型分成三个固定角色，配置保存在数据库 `model_providers` 表中，随数据迁移一起打包。

| 角色 | `category` | 用途 |
| --- | --- | --- |
| 主模型 | `chat` | 对话、推理、决定是否调用语音/图片工具 |
| 语音模型 | `speech` | 把文本合成为语音 |
| 图片模型 | `image` | 根据提示词生成图片 |

三类模型都通过统一的配置界面管理。适配器分两层：

1. **OpenAI 兼容适配器**：覆盖大多数厂商的兼容端点。
2. **原生适配器**：协议差异较大的供应商单独实现。

## 1. 兼容矩阵

| 适配器 | 覆盖范围 | 支持类别 |
| --- | --- | --- |
| `openai_compatible` | OpenAI、DeepSeek、通义千问、Kimi、智谱 GLM、豆包/火山方舟、SiliconFlow、OpenRouter、Groq、Mistral、xAI、Together、Perplexity、百度千帆、腾讯混元、讯飞星火、NVIDIA NIM、Cerebras、Ollama、LM Studio、任意自定义兼容网关 | chat / speech / image |
| `azure_openai` | Azure OpenAI 部署 | chat / speech / image |
| `anthropic` | Anthropic Claude Messages API | chat |
| `google_gemini` | Gemini 对话模型与 Gemini 图片模型 | chat / image |
| `elevenlabs` | ElevenLabs 文本转语音 | speech |
| `minimax` | MiniMax 对话、同步 T2A 语音与 H3 图片生成 | chat / speech / image |

控制台提供供应商预设，选择预设会自动填充 Provider 类型和 Base URL；模型名称仍需从官方接口获取或手动输入。也可以选择「自定义 / OpenAI 兼容」手动填写任意端点。

语音预设覆盖 OpenAI、Azure OpenAI、ElevenLabs、MiniMax、Groq Orpheus、Together AI 和 SiliconFlow CosyVoice；图片预设覆盖 OpenAI、Azure OpenAI、Gemini、MiniMax H3、Together AI FLUX、SiliconFlow FLUX/Kolors、DeepInfra FLUX 和火山方舟 Seedream。MiniMax 国际版与国内版使用不同域名，API Key 不能混用。

### 1.1 从供应商获取模型列表

模型名称不再写死在代码里。填写 Base URL 和 API Key 后，点击模型输入框右侧的刷新按钮，MoriBot 会直接请求供应商的官方模型接口：

| 供应商类型 | 模型列表接口 |
| --- | --- |
| `openai_compatible` | `GET {base_url}/models` |
| `anthropic` | `GET {base_url}/models` |
| `google_gemini` | `GET {base_url}/models` |
| `azure_openai` | `GET {base_url}/openai/models?api-version=...` |
| `elevenlabs` | `GET {base_url}/models` |

返回的列表会按当前角色过滤：主模型排除 embedding、TTS、图片生成等模型；语音模型只保留 TTS/语音模型；图片模型只保留图片生成模型。若供应商没有返回可识别列表，界面会提示失败原因并保留手动输入，不会阻塞保存。

MiniMax 的 `/models` 接口会同时返回已下线的 `MiniMax-M2.x` 系列，MoriBot 会根据 `config.json` 中 `provider.retired_model_prefixes` 自动过滤；该接口只列出对话模型，因此语音/图片分类会使用 `provider.media_model_fallbacks` 的条目。后续 MiniMax 更新模型时，只需修改配置并重启，不需要改代码。

获取模型列表的同时会解析能力信息并写入 `capabilities`：

```json
{
  "input": ["text", "image"],
  "output": ["text"],
  "tools": true,
  "reasoning": false,
  "context_window": 128000,
  "source": "api"
}
```

- `input` / `output`：支持的输入、输出模态（`text`、`image`、`audio`、`video`）。
- `tools`：是否支持工具调用；主模型据此决定是否发送 `tools`。
- `reasoning`：是否为推理模型，便于后续调整参数。
- `context_window`：上下文窗口大小。
- `source`：`api` 表示来自供应商元数据，`heuristic` 表示按模型名推断，`manual` 表示用户手动填写。

OpenRouter、Gemini 等会返回 `architecture`、`inputTokenLimit` 等元数据；OpenAI 等只返回模型 ID 的供应商会按模型名做保守推断（例如含 `gpt-4o`、`vl`、`claude`、`gemini` 视为支持图片输入）。推断结果会随配置持久化，对话层读取同一份能力，不需要再猜。

### 1.2 参数预设

主模型的 `temperature` 和 `max_tokens` 对新手不直观，配置界面提供预设：

| 预设 | temperature | max_tokens | 适用场景 |
| --- | --- | --- | --- |
| 平衡（推荐） | 0.7 | 2048 | 日常对话 |
| 精确稳定 | 0.2 | 1024 | 事实问答、结构化输出 |
| 创意发散 | 1.0 | 4096 | 写作、头脑风暴 |
| 自定义 | 手动 | 手动 | 高级用户 |

选择预设会自动填入参数，手动修改任一参数会切回「自定义」。语音和图片模型不显示该预设，而是给出音色/格式/尺寸等说明。

### 1.3 常用 Base URL

| 供应商 | Base URL |
| --- | --- |
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 通义千问 / DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Moonshot / Kimi | `https://api.moonshot.cn/v1` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| MiniMax（国际） | `https://api.minimax.io/v1` |
| MiniMax（国内） | `https://api.minimax.cn/v1` |
| 火山方舟 / 豆包 | `https://ark.cn-beijing.volces.com/api/v3` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| xAI | `https://api.x.ai/v1` |
| 百度千帆 | `https://qianfan.baidubce.com/v2` |
| 腾讯混元 | `https://api.hunyuan.cloud.tencent.com/v1` |
| 讯飞星火 | `https://spark-api-open.xf-yun.com/v1` |
| Ollama | `http://127.0.0.1:11434/v1` |
| LM Studio | `http://127.0.0.1:1234/v1` |

## 2. 配置步骤

1. 登录后台，打开左侧「模型服务」。
2. 在「主模型 / 语音模型 / 图片模型」中分别点击「添加模型」。
3. 选择供应商预设，或选择「自定义 / OpenAI 兼容」，填写名称、Base URL、API Key。
4. 点击模型输入框右侧的刷新按钮，从供应商官方接口获取模型列表并下拉选择；无法获取时可手动输入模型名称。
5. 查看模型能力标签（图片识别、工具调用、推理、上下文），确认是否符合预期。
6. 主模型可选择参数预设，或手动调整 `temperature`、`max_tokens`；语音/图片模型按提示填写音色、格式、尺寸等。
7. 保存后点击「测试连接」发起一次真实的小请求。
8. 每种类型可以配置多个，点击「设为默认」切换默认模型。

「测试连接」的请求已经尽量最小化：主模型发送 `Hi` 并限制 8 个输出 token；语音模型合成 `Hi.`；图片模型只生成 1 张图。主模型和语音测试通常可在几秒内完成；图片生成以及供应商冷启动、排队和网络延迟仍可能让测试耗时较长，并产生少量费用。

没有 API Key 的本地服务可以留空。API Key 使用安装密钥派生的 Fernet 加密后保存到数据库，API 响应只返回 `api_key_set` 和末尾提示，不返回明文。

## 3. 主模型如何调用语音和图片

`ModelGateway` 把已配置的语音、图片默认模型暴露为主模型的工具：

```text
用户消息
  └─ 主模型 chat.completions(tools=[generate_speech, generate_image])
       ├─ tool_call: generate_speech(text, voice?)
       │    └─ 语音模型 /audio/speech → SpeechResult(audio bytes)
       ├─ tool_call: generate_image(prompt, size?)
       │    └─ 图片模型 /images/generations → GeneratedImage[]
       └─ 主模型收到 tool 结果，继续生成最终文本
```

返回对象：

```python
ModelReply(
    text="这是最终文字回复",
    speech=SpeechResult(...),  # 可选
    images=[GeneratedImage(...)],  # 可选
)
```

实现：`moribot/core/provider/gateway.py`。后续对话服务只需要：

```python
reply = await core.model_gateway.chat(messages)
```

然后把 `reply.text`、`reply.speech`、`reply.images` 分别映射为 MoriMobile 的文字、语音和图片消息。

工具只在对应默认模型存在时才会出现在主模型的 tools 列表中；没有配置语音/图片模型时，主模型只做普通对话。

## 4. API

所有接口需要后台 JWT：

```http
GET    /api/v1/providers
GET    /api/v1/providers/catalog
POST   /api/v1/providers/models
POST   /api/v1/providers
PATCH  /api/v1/providers/{id}
DELETE /api/v1/providers/{id}
POST   /api/v1/providers/{id}/default
POST   /api/v1/providers/{id}/test
```

`POST /api/v1/providers/models` 请求体：

```json
{
  "provider_type": "openai_compatible",
  "category": "chat",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "provider_id": 1,
  "options": {}
}
```

传 `provider_id` 时可以不传 `api_key`，后端会解密已保存的密钥。接口失败时仍返回 200，通过 `message` 说明原因，`manual_allowed` 表示可以继续手动输入。

创建示例：

```bash
curl -X POST http://127.0.0.1:6186/api/v1/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "chat",
    "name": "OpenAI Main",
    "provider_type": "openai_compatible",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4.1-mini",
    "options": {"temperature": 0.7, "max_tokens": 2048},
    "is_default": true
  }'
```

更新时把 `api_key` 留空或不传，会保留原密钥。

## 5. 数据结构

`model_providers` 表：

| 字段 | 说明 |
| --- | --- |
| `category` | `chat` / `speech` / `image` |
| `name` | 同一类型下唯一的显示名 |
| `provider_type` | `openai_compatible` / `anthropic` / `google_gemini` / `azure_openai` / `elevenlabs` / `minimax` |
| `base_url` | 接口根地址 |
| `api_key_encrypted` | Fernet 密文 |
| `model` | 模型名 |
| `options` | 类型相关参数 JSON |
| `capabilities` | 模型能力 JSON（输入/输出模态、工具、推理、上下文） |
| `is_default` | 该类型默认模型 |
| `enabled` | 是否参与加载 |
| `last_test_*` | 最近一次连通性测试结果 |

由于模型配置在数据库中，备份/迁移会自动携带，不需要额外操作。API Key 能否解密取决于 `config.json` 中的 JWT 密钥是否一起迁移；迁移时请完整导入备份。旧版本数据库启动时会自动执行 `ALTER TABLE model_providers ADD COLUMN capabilities` 补齐字段，已有配置仍然可用。

## 6. 当前限制

- 原生适配器当前覆盖 Anthropic、Gemini、Azure OpenAI、ElevenLabs、MiniMax；其余厂商通过 OpenAI 兼容端点接入。
- MiniMax 语音使用原生 `POST /v1/t2a_v2` 接口（返回 hex 音频），图片使用 H3 的 `/v1/images/generations`；国际账号使用 `api.minimax.io`，国内账号使用 `api.minimax.cn`，两者的 API Key 不能混用。国内语音如要求 `GroupId`，可在配置的 `options.group_id` 中补充。
- MiniMax 的 `/models` 不返回语音/图片模型，相关下拉项来自 `config.json` 的 `provider.media_model_fallbacks`；已下线模型通过 `provider.retired_model_prefixes` 过滤。更新模型无需改代码。
- 百度文心、腾讯混元、讯飞星火等原生签名协议未单独实现，请使用其 OpenAI 兼容入口或自建网关。
- Gemini 目前支持 Gemini Image（`gemini-2.5-flash-image`），暂未接入 Imagen `:predict` 与 Gemini TTS。
- 部分供应商的 `/models` 只返回模型 ID，不返回模态；此时 `capabilities.source` 为 `heuristic`，按名称推断，用户仍可手动修改模型名后重新获取。
- 连通性测试会发起真实请求，可能产生少量费用。
- 主模型的流式输出、自动重试和多轮 Agent 循环仍在后续计划中。
- 图片/语音工具每轮返回最近一次结果；多张图片可在 `GeneratedImage` 列表中扩展。
