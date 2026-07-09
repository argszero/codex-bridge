# Responses API 详细文档

> 来源: OpenAI 官方 API Reference (`developers.openai.com`)
> 端点: `POST https://api.openai.com/v1/responses`

## 概述

创建模型响应。提供文本或图像输入来生成文本或 JSON 输出。可以让模型调用你的自定义代码或使用内置工具（如网络搜索、文件搜索）。

---

## 请求体 (Request Body)

### 必填参数

无严格必填参数（所有参数均为 optional），但通常需要提供 `model` 和 `input`。

### 核心参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | `string` (ResponsesModel) | 模型 ID，如 `gpt-4o`、`o3` 等 |
| `input` | `string` \| `array` | **核心区别** — 文本、图像或文件输入。结构比 Chat 的 `messages` 更加多元化 |

### 全部可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `background` | `boolean` | - | 是否在后台运行模型响应 |
| `context_management` | `array of { type, compact_threshold }` | - | 上下文管理配置 |
| `conversation` | `string` \| `ResponseConversationParam` | - | 所属对话。对话中的历史 items 会自动加入该次请求 |
| `include` | `array of ResponseIncludable` | - | 指定要包含的额外输出数据。支持的值见下方 |
| `input` | `string` \| `array` | - | 输入内容，详见 [Input 结构](#input-结构) |
| `instructions` | `string` | - | **核心区别** — 系统/开发者消息，作为顶层参数而非 messages 中的一条 |
| `max_output_tokens` | `number` | - | 生成 token 上限 (min: 16) |
| `max_tool_calls` | `number` | - | 整个响应中内置工具调用的最大总次数 |
| `metadata` | `object` | - | 最多 16 对键值对 |
| `moderation` | `{ model }` | - | 内容审核配置 |
| `parallel_tool_calls` | `boolean` | - | 是否允许并行工具调用 |
| `previous_response_id` | `string` | - | **核心区别** — 通过引用上一次 response ID 实现多轮对话（不能与 conversation 同时使用） |
| `prompt` | `{ id, variables, version }` | - | 引用 prompt 模板 |
| `prompt_cache_key` | `string` | - | 缓存优化 |
| `prompt_cache_retention` | `"in_memory"` \| `"24h"` | - | 缓存保留策略。对于 gpt-5.5+ 仅支持 `24h` |
| `reasoning` | `{ context, effort, generate_summary, summary }` | - | **核心区别** — gpt-5 和 o-series 推理配置（Chat 用 `reasoning_effort`） |
| `safety_identifier` | `string` | - | 用户标识符 (max 64 字符) |
| `service_tier` | `"auto"` \| `"default"` \| `"flex"` \| `"priority"` | `"auto"` | 服务等级 |
| `store` | `boolean` | - | 是否存储响应供后续 API 检索 |
| `stream` | `boolean` | - | 是否 SSE 流式返回 |
| `stream_options` | `{ include_obfuscation }` | - | 流式选项 |
| `temperature` | `number` | - | 采样温度 (0-2) |
| `text` | `{ format, verbosity }` | `{ type: "text" }` | **核心区别** — 文本输出配置（Chat 用 `response_format`） |
| `tool_choice` | `ToolChoiceOptions` \| `ToolChoiceAllowed` \| ... | - | 工具选择策略 |
| `tools` | `array` | - | 可用工具列表。支持：内置工具、MCP 工具、自定义函数工具 |
| `top_logprobs` | `number` | - | 返回的最可能 token 数量 (0-20) |
| `top_p` | `number` | - | nucleus sampling (0-1) |

### 已弃用参数

| 参数 | 替代 |
|------|------|
| `truncation` | 自动处理 |
| `user` | `safety_identifier` + `prompt_cache_key` |

### Include 参数支持的值

- `web_search_call.action.sources` — 包含网络搜索来源
- `code_interpreter_call.outputs` — 包含代码执行输出
- `computer_call_output.output.image_url` — 包含计算机操作截图
- `file_search_call.results` — 包含文件搜索结果
- `message.input_image.image_url` — 包含输入图像 URL
- `message.output_text.logprobs` — 包含 logprobs
- `reasoning.encrypted_content` — 包含推理 token 加密版本

---

## Input 结构

`input` 是 Responses API 与 Chat Completions API 最大的区别之一。它可以是一个字符串，也可以是一个类型化 item 数组。

### 字符串形式
```json
{ "model": "gpt-5.4", "input": "Tell me a bedtime story." }
```

### 数组形式 — 类型化 Input Items

#### ResponseInputMessageItem (消息输入)
```json
{
  "type": "message",
  "role": "user | system | developer | assistant",
  "id": "optional string",
  "content": "string | ResponseInputContent[]",
  "status": "optional"
}
```

其中 `ResponseInputContent` 可以是：
- **Text**: `{ "type": "input_text", "text": "string" }`
- **Image**: `{ "type": "input_image", "image_url": "string", "file_id": "string", "detail": "auto|low|high" }`
- **File**: `{ "type": "input_file", "file_data": "...", "file_id": "..." }`
- **Audio**: `{ "type": "input_audio", "input_audio": { "data": "...", "format": "..." } }`

#### ResponseOutputMessage (助手消息，用于多轮对话历史)
```json
{
  "type": "message",
  "id": "msg_xxx",
  "role": "assistant",
  "status": "completed",
  "content": [
    { "type": "output_text", "text": "string", "annotations": [] }
  ]
}
```

#### Function Call (工具调用)
```json
{
  "type": "function_call",
  "id": "fc_xxx",
  "call_id": "call_xxx",
  "name": "function_name",
  "arguments": "{\"key\": \"value\"}",
  "status": "completed | in_progress | incomplete"
}
```

#### Function Call Output (工具调用结果)
```json
{
  "type": "function_call_output",
  "call_id": "call_xxx",
  "output": "string or object",
  "status": "completed"
}
```

#### Reasoning (推理项)
```json
{
  "type": "reasoning",
  "id": "rsn_xxx",
  "content": [
    { "type": "reasoning_text", "text": "string" }
  ],
  "status": "completed"
}
```

---

## 工具 (Tools) 结构

Responses API 支持三类工具：

### 1. 自定义函数工具 (Function Tools)
```json
{
  "type": "function",
  "name": "get_weather",
  "description": "Get current weather",
  "parameters": { "type": "object", "properties": { ... }, "required": [] }
}
```

### 2. 内置工具 (Built-in Tools)
```json
// 网络搜索
{ "type": "web_search", "search_context_size": "low|medium|high", "user_location": { ... } }

// 文件搜索
{ "type": "file_search", "vector_store_ids": ["vs_xxx"], "max_num_results": 10 }

// 代码解释器
{ "type": "code_interpreter" }

// 计算机操作
{ "type": "computer_use", "environment": "local" }
```

### 3. MCP 工具
```json
{ "type": "mcp", "server_label": "server_name", ... }
```

### Tool Choice 选项
- `"auto"` — 自动选择
- `"none"` — 不调用工具
- `"required"` — 必须调用工具
- `{ "type": "function", "name": "my_function" }` — 指定具体函数

---

## 响应体 (Response Body)

### Response 对象

```json
{
  "id": "resp_xxx",                      // 唯一标识符，格式 resp_...
  "object": "response",                  // 固定值 "response"
  "created_at": 1741476542,              // Unix 时间戳
  "status": "completed",                 // 状态: completed, in_progress, incomplete, failed, queued
  "completed_at": 1741476543,            // 完成时间戳
  "error": null,                         // 错误信息 (失败时)
  "incomplete_details": null,            // 不完整原因
  "instructions": null,                  // 回显 instructions
  "max_output_tokens": null,             // 回显 max_output_tokens
  "model": "gpt-5.4",                    // 使用的模型
  "output": [                            // ★核心区别 — 类型化的输出 item 数组
    {
      "type": "message",                 // item 类型: message | reasoning | function_call | ...
      "id": "msg_xxx",
      "status": "completed",
      "role": "assistant",
      "content": [                       // 内容也是类型化数组
        {
          "type": "output_text",
          "text": "response text...",
          "annotations": []
        }
      ]
    },
    {
      "type": "reasoning",               // ★推理作为独立的输出 item
      "id": "rsn_xxx",
      "status": "completed",
      "content": [
        {
          "type": "reasoning_text",
          "text": "reasoning content..."
        }
      ]
    },
    {
      "type": "function_call",           // ★工具调用作为独立的输出 item
      "id": "fc_call_xxx",
      "call_id": "call_xxx",
      "name": "function_name",
      "arguments": "{\"key\":\"value\"}",
      "status": "completed"
    }
  ],
  "parallel_tool_calls": true,           // 回显
  "previous_response_id": null,          // 回显
  "reasoning": {                         // 回显推理配置
    "effort": null,
    "summary": null
  },
  "store": true,                         // 回显
  "temperature": 1.0,                    // 回显
  "text": {                              // 回显文本配置
    "format": { "type": "text" }
  },
  "tool_choice": "auto",                 // 回显
  "tools": [],                           // 回显
  "top_p": 1.0,                          // 回显
  "truncation": "disabled",              // 回显 (已弃用)
  "usage": {                             // 使用量统计
    "input_tokens": 36,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 87,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 123
  },
  "user": null,                          // 回显
  "metadata": {}                         // 回显
}
```

### Output Item 类型汇总

| Type | 说明 | 关键字段 |
|------|------|----------|
| `message` | 助手消息 | `role: "assistant"`, `content[]` |
| `reasoning` | 推理内容（独立 item） | `content: [{ type: "reasoning_text", text }]` |
| `function_call` | 函数调用 | `call_id`, `name`, `arguments` |
| `web_search_call` | 网络搜索调用 | - |
| `file_search_call` | 文件搜索调用 | - |
| `code_interpreter_call` | 代码解释器调用 | `code`, `outputs` |
| `computer_call` | 计算机操作调用 | - |
| `image_gen_call` | 图像生成调用 | - |
| `mcp_call` | MCP 工具调用 | - |
| `shell_call` | Shell 命令调用 | - |

---

## 流式响应 (Streaming SSE)

当 `stream: true` 时，响应通过 Server-Sent Events 返回。与 Chat SSE 的 delta 模型不同，Responses API **发出类型化事件**。

### 流式事件类型

#### 生命周期事件

| 事件 | 时机 | 关键数据 |
|------|------|----------|
| `response.created` | 响应对象创建 | `{ response: { id, status: "in_progress", model, output: [] } }` |
| `response.in_progress` | 响应开始处理 | `{ response_id }` |
| `response.queued` | 响应排队等待 | `{ response }` |
| `response.completed` | 响应完成 | `{ response: { id, status, model, output, usage } }` |
| `response.incomplete` | 响应未完成就结束 | `{ response }` |
| `error` | 发生错误 | `{ type: "error", code, message }` |

#### Output Item 事件

| 事件 | 时机 | 关键数据 |
|------|------|----------|
| `response.output_item.added` | 新输出 item 被添加 | `{ output_index, item: { id, type, status: "in_progress" } }` |
| `response.output_item.done` | 输出 item 完成 | `{ output_index, item: { id, type, status: "completed", content } }` |

#### 文本内容事件

| 事件 | 时机 | 关键数据 |
|------|------|----------|
| `response.content_part.added` | 内容部分被添加 | `{ item_id, output_index, content_index, part }` |
| `response.output_text.delta` | 文本增量 | `{ item_id, output_index, content_index, delta: "string" }` |
| `response.content_part.done` | 内容部分完成 | `{ item_id, output_index, content_index, part }` |
| `response.output_text.done` | 文本内容完成 | `{ item_id, output_index, content_index, text }` |

#### 推理内容事件

| 事件 | 时机 | 关键数据 |
|------|------|----------|
| `response.reasoning_text.delta` | 推理文本增量 | `{ item_id, output_index, content_index, delta: "string" }` |
| `response.reasoning_text.done` | 推理文本完成 | `{ item_id, output_index, content_index, text }` |
| `response.reasoning_summary_part.added` | 推理摘要添加 | `{ item_id, output_index, part }` |
| `response.reasoning_summary_text.delta` | 推理摘要增量 | `{ item_id, output_index, content_index, delta }` |
| `response.reasoning_summary_text.done` | 推理摘要完成 | `{ item_id, output_index, content_index, text }` |

#### 函数调用事件

| 事件 | 时机 | 关键数据 |
|------|------|----------|
| `response.function_call_arguments.delta` | 函数参数增量 | `{ item_id, output_index, delta: "string" }` |
| `response.function_call_arguments.done` | 函数参数完成 | `{ item_id, output_index, arguments, name, call_id }` |

#### 其他工具事件

| 事件 | 说明 |
|------|------|
| `response.web_search_call.in_progress` | 网络搜索开始 |
| `response.web_search_call.searching` | 网络搜索进行中 |
| `response.web_search_call.completed` | 网络搜索完成 |
| `response.file_search_call.in_progress` | 文件搜索开始 |
| `response.file_search_call.searching` | 文件搜索进行中 |
| `response.file_search_call.completed` | 文件搜索完成 |
| `response.code_interpreter_call.in_progress` | 代码解释器开始 |
| `response.code_interpreter_call.code.delta` | 代码增量 |
| `response.code_interpreter_call.code.done` | 代码完成 |
| `response.code_interpreter_call.completed` | 代码执行完成 |
| `response.image_gen_call.in_progress` | 图像生成开始 |
| `response.image_gen_call.generating` | 图像生成中 |
| `response.image_gen_call.partial_image` | 部分图像可用 |
| `response.image_gen_call.completed` | 图像生成完成 |
| `response.mcp_call.in_progress` | MCP 调用开始 |
| `response.mcp_call.arguments.delta` | MCP 参数增量 |
| `response.mcp_call.arguments.done` | MCP 参数完成 |
| `response.mcp_call.completed` | MCP 调用完成 |
| `response.mcp_call.failed` | MCP 调用失败 |
| `response.mcp_list_tools.in_progress` | MCP 列出工具开始 |
| `response.mcp_list_tools.completed` | MCP 列出工具完成 |

### 流结束标志

```
event: done
data: [DONE]
```

---

## 示例

### 请求（简单文本）
```bash
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-5.4",
    "input": "Tell me a three sentence bedtime story about a unicorn."
  }'
```

### 请求（带工具调用）
```bash
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-5.4",
    "input": "What is the weather in Tokyo?",
    "tools": [
      {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather",
        "parameters": {
          "type": "object",
          "properties": {
            "location": { "type": "string" }
          },
          "required": ["location"]
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

### 请求（多轮对话，使用 previous_response_id）
```json
{
  "model": "gpt-5.4",
  "input": "What about the weather in Osaka?",
  "previous_response_id": "resp_xxx"
}
```

### 响应
```json
{
  "id": "resp_67ccd2bed1ec8190b14f964abc0542670bb6a6b452d3795b",
  "object": "response",
  "created_at": 1741476542,
  "status": "completed",
  "completed_at": 1741476543,
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-5.4",
  "output": [
    {
      "type": "message",
      "id": "msg_67ccd2bf17f0819081ff3bb2cf6508e60bb6a6b452d3795b",
      "status": "completed",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "In a peaceful grove beneath a silver moon, a unicorn named Lumina discovered a hidden pool that reflected the stars...",
          "annotations": []
        }
      ]
    }
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": { "effort": null, "summary": null },
  "store": true,
  "temperature": 1.0,
  "text": { "format": { "type": "text" } },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 36,
    "input_tokens_details": { "cached_tokens": 0 },
    "output_tokens": 87,
    "output_tokens_details": { "reasoning_tokens": 0 },
    "total_tokens": 123
  },
  "user": null,
  "metadata": {}
}
```
