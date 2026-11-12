# 模型配置与工具调用

MoriBot 把模型分成三个固定角色，配置保存在数据库 `model_providers` 表中，随数据迁移一起打包。

| 角色 | `category` | 用途 |
| --- | --- | --- |
| 主模型 | `chat` | 对话、推理、决定是否调用语音/图片工具 |
| 语音模型 | `speech` | 把文本合成为语音 |
| 图片模型 | `image` | 根据提示词生成图片 |

三类模型都使用 **OpenAI 兼容接口**：

- 主模型：`POST {base_url}/chat/completions`
- 语音模型：`POST {base_url}/audio/speech`
- 图片模型：`POST {base_url}/images/generations`

`base_url` 应填写接口根路径，例如：

```text
https://api.openai.com/v1
https://your-oneapi.example.com/v1
http://127.0.0.1:1234/v1     # LM Studio 等本地服务
```

## 1. 在控制台配置

1. 登录后台，打开左侧「模型服务」。
2. 在「主模型 / 语音模型 / 图片模型」中分别点击「添加模型」。
3. 填写名称、Base URL、API Key、模型名称。
4. 根据类型填写可选参数：
   - 主模型：`temperature`、`max_tokens`
   - 语音模型：`voice`、音频格式、`speed`
   - 图片模型：尺寸、质量、数量、返回格式
5. 保存后点击「测试连接」发起一次真实的小请求。
6. 每种类型可以配置多个，点击「设为默认」切换默认模型。

没有 API Key 的本地服务可以留空。API Key 使用安装密钥派生的 Fernet 加密后保存到数据库，API 响应只返回 `api_key_set` 和末尾提示，不返回明文。

## 2. 主模型如何调用语音和图片

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

## 3. API

所有接口需要后台 JWT：

```http
GET    /api/v1/providers
POST   /api/v1/providers
PATCH  /api/v1/providers/{id}
DELETE /api/v1/providers/{id}
POST   /api/v1/providers/{id}/default
POST   /api/v1/providers/{id}/test
```

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

## 4. 数据结构

`model_providers` 表：

| 字段 | 说明 |
| --- | --- |
| `category` | `chat` / `speech` / `image` |
| `name` | 同一类型下唯一的显示名 |
| `provider_type` | 当前为 `openai_compatible` |
| `base_url` | 接口根地址 |
| `api_key_encrypted` | Fernet 密文 |
| `model` | 模型名 |
| `options` | 类型相关参数 JSON |
| `is_default` | 该类型默认模型 |
| `enabled` | 是否参与加载 |
| `last_test_*` | 最近一次连通性测试结果 |

由于模型配置在数据库中，备份/迁移会自动携带，不需要额外操作。API Key 能否解密取决于 `config.json` 中的 JWT 密钥是否一起迁移；迁移时请完整导入备份。

## 5. 当前限制

- 只实现了 OpenAI 兼容协议；Anthropic、Gemini 原生协议尚未接入。
- 连通性测试会发起真实请求，可能产生少量费用。
- 主模型的流式输出、自动重试和多轮 Agent 循环仍在后续计划中。
- 图片/语音工具每轮返回最近一次结果；多张图片可在 `GeneratedImage` 列表中扩展。
