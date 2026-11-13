# 角色卡与模型覆盖

角色卡用于定义 MoriBot 的角色人设，并允许为不同角色选择不同的对话、语音和图片模型。

## 1. 角色卡字段

| 字段 | 说明 |
| --- | --- |
| `name` | 角色名称，全局唯一 |
| `avatar` | 头像 URL；由上传接口生成并随角色卡保存 |
| `description` | 角色简介 |
| `persona` | 人物设定，描述性格、背景、说话方式、行为准则等，可写一大段文本 |
| `chat_provider_id` | 对话主模型覆盖；`null` 表示跟随系统默认 |
| `speech_provider_id` | 语音模型覆盖；`null` 表示跟随系统默认 |
| `image_provider_id` | 图片模型覆盖；`null` 表示跟随系统默认 |
| `enabled` | 是否启用 |

模型覆盖只接受对应类别的 Provider。例如 `chat_provider_id` 必须是 `chat` 类型，否则接口返回 400。

## 2. 模型解析规则

```text
角色指定了 chat_provider_id 且模型仍存在
  → 使用角色指定模型
否则
  → 使用该类别当前启用的默认模型
```

语音、图片模型使用相同规则。这样角色卡既可以选择非默认模型，也可以始终跟随系统默认模型。

删除 Provider 时，引用它的角色卡会自动把对应字段清空，回退到系统默认模型。

## 3. 头像

头像只能通过管理页上传：

- 头像旁有一个紧凑的「上传头像」按钮。
- 鼠标悬浮已上传的头像时，会显示「预览」按钮。
- 支持 PNG / JPEG / WebP / GIF，最大 2 MB。
- 上传后文件保存在数据目录的 `avatars/` 下，并生成 `/avatars/<filename>` URL 随角色卡一起保存。
- 该 URL 可直接提供给 MoriMobile 显示头像。
- 头像随数据备份一起迁移。
- 更新头像或删除角色时会清理旧本地头像。

## 4. API

所有接口需要后台 JWT：

```http
GET    /api/v1/characters
POST   /api/v1/characters
GET    /api/v1/characters/{id}
PATCH  /api/v1/characters/{id}
DELETE /api/v1/characters/{id}
POST   /api/v1/characters/avatar
```

创建示例：

```bash
curl -X POST http://127.0.0.1:6186/api/v1/characters \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "小森",
    "avatar": "/avatars/2f8c....png",
    "description": "森林里的向导",
    "persona": "温柔、耐心，喜欢自然。你说话缓慢而清楚，会先倾听再回答。",
    "chat_provider_id": null,
    "speech_provider_id": 3,
    "image_provider_id": null,
    "enabled": true
  }'
```

头像上传：

```json
{
  "data_url": "data:image/png;base64,..."
}
```
