# Chat Completions API 详细文档

> 来源: OpenAI 官方 API Reference (`developers.openai.com`)
> 端点: `POST https://api.openai.com/v1/chat/completions`

## 概述

给定一组消息组成的对话，模型将返回一个响应。

---

## 请求体 (Request Body)

### 必填参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | `string` | 模型 ID，如 `gpt-4o`、`o3` 等 |
| `messages` | `array of ChatCompletionMessageParam` | 组成对话的消息列表 |

### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `audio` | `{ format, voice }` | - | 音频输出参数，需要 `modalities: ["audio"]` |
| `frequency_penalty` | `number` | - | -2.0 到 2.0，根据 token 出现频率惩罚重复 |
| `logit_bias` | `map[number]` | - | 修改特定 token 出现概率的偏置值 (-100 到 100) |
| `logprobs` | `boolean` | - | 是否返回输出 token 的 log 概率 |
| `max_completion_tokens` | `number` | - | 生成 token 的上限（含 reasoning tokens） |
| `metadata` | `object` | - | 最多 16 对键值对，key≤64 字符，value≤512 字符 |
| `modalities` | `array of "text" \| "audio"` | `["text"]` | 输出模态 |
| `moderation` | `{ model }` | - | 对输入和输出进行内容审核 |
| `n` | `number` | `1` | 为每条输入生成多少个 completion 选项 (1-128) |
| `parallel_tool_calls` | `boolean` | - | 是否允许并行工具调用 |
| `prediction` | `{ content, type }` | - | 静态预测输出内容 |
| `presence_penalty` | `number` | - | -2.0 到 2.0，根据主题多样性惩罚 |
| `prompt_cache_key` | `string` | - | 用于缓存优化（替代 `user` 字段） |
| `prompt_cache_retention` | `"in_memory"` \| `"24h"` | - | prompt 缓存保留策略 |
| `reasoning_effort` | `ReasoningEffort` | 模型相关 | 推理力度: `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |
| `response_format` | `{ type }` | - | 输出格式: `text`, `json_object`, `json_schema` |
| `safety_identifier` | `string` | - | 用户标识符 (max 64 字符)，用于安全检测 |
| `service_tier` | `"auto"` \| `"default"` \| `"flex"` \| `"priority"` | `"auto"` | 服务等级 |
| `stop` | `string` \| `array of string` | - | 最多 4 个停止序列 |
| `store` | `boolean` | - | 是否存储输出用于模型蒸馏或评估 |
| `stream` | `boolean` | - | 是否使用 SSE 流式返回 |
| `stream_options` | `{ include_obfuscation, include_usage }` | - | 流式选项（仅在 stream: true 时设置） |
| `temperature` | `number` | - | 采样温度 (0-2) |
| `tool_choice` | `ChatCompletionToolChoiceOption` | - | 工具选择策略: `none`, `auto`, `required` 或指定工具 |
| `tools` | `array of ChatCompletionTool` | - | 可用工具列表（函数工具或自定义工具） |
| `top_logprobs` | `number` | - | 返回的最可能 token 数量 (0-20)，需 `logprobs: true` |
| `top_p` | `number` | - | nucleus sampling 参数 (0-1) |
| `verbosity` | `"low"` \| `"medium"` \| `"high"` | - | 响应详细程度 |
| `web_search_options` | `{ search_context_size, user_location }` | - | 网络搜索选项 |

### 已弃用参数

| 参数 | 替代 |
|------|------|
| `function_call` | `tool_choice` |
| `functions` | `tools` |
| `max_tokens` | `max_completion_tokens` |
| `seed` | - |
| `user` | `safety_identifier` + `prompt_cache_key` |

---

## Messages 结构

`messages` 是一个消息数组，每个消息的类型如下：

### ChatCompletionDeveloperMessageParam
```json
{ "role": "developer", "content": "string", "name": "optional string" }
```
> 在 o1 及更新模型中，`developer` 角色替代了 `system` 角色

### ChatCompletionSystemMessageParam
```json
{ "role": "system", "content": "string", "name": "optional string" }
```

### ChatCompletionUserMessageParam
```json
{ "role": "user", "content": "string | ChatCompletionContentPart[]", "name": "optional string" }
```

其中 `ChatCompletionContentPart` 可以是：
- **Text**: `{ "type": "text", "text": "string" }`
- **Image**: `{ "type": "image_url", "image_url": { "url": "string" } }`
- **Input Audio**: `{ "type": "input_audio", "input_audio": { "data": "string", "format": "string" } }`

### ChatCompletionAssistantMessageParam
```json
{
  "role": "assistant",
  "content": "string | null",
  "refusal": "string | null",
  "audio": { "id": "string" } | null,
  "tool_calls": ChatCompletionMessageToolCall[],
  "function_call": { "name": "string", "arguments": "string" }
}
```

### ChatCompletionToolMessageParam
```json
{
  "role": "tool",
  "content": "string",
  "tool_call_id": "string"
}
```

### ChatCompletionFunctionMessageParam
```json
{
  "role": "function",
  "content": "string",
  "name": "string"
}
```

---

## 工具 (Tools) 结构

### Function Tool
```json
{
  "type": "function",
  "function": {
    "name": "string",
    "description": "string",
    "parameters": { "type": "object", "properties": {}, "required": [] }
  }
}
```

### Custom Tool
```json
{
  "type": "custom",
  "custom": { ... }
}
```

### Tool Choice 选项
- `"none"` — 不调用工具
- `"auto"` — 自动选择（有工具时的默认值）
- `"required"` — 必须调用工具
- `{ "type": "function", "function": { "name": "my_function" } }` — 指定具体函数

---

## 响应体 (Response Body)

### ChatCompletion 对象

```json
{
  "id": "chatcmpl-xxx",           // 唯一标识符
  "object": "chat.completion",     // 固定值
  "created": 1741569952,           // Unix 时间戳
  "model": "gpt-5.4",              // 使用的模型
  "choices": [                     // 完成选项数组
    {
      "index": 0,                  // 选项索引
      "message": {                 // ChatCompletionMessage
        "role": "assistant",       // 角色
        "content": "string",       // 文本内容
        "refusal": "string | null", // 安全拒绝信息
        "annotations": [],         // 注解
        "audio": {                 // 音频输出 (可选)
          "id": "string",
          "data": "string",
          "expires_at": 0,
          "transcript": "string"
        },
        "tool_calls": [            // 工具调用
          {
            "id": "string",
            "type": "function",
            "function": {
              "name": "string",
              "arguments": "string"
            }
          }
        ],
        "function_call": { "name": "string", "arguments": "string" }  // 已弃用
      },
      "logprobs": {                // log 概率 (可选)
        "content": [
          {
            "token": "string",
            "bytes": [],
            "logprob": 0.0,
            "top_logprobs": []
          }
        ],
        "refusal": null
      },
      "finish_reason": "stop"      // 停止原因: stop, length, tool_calls, content_filter, function_call
    }
  ],
  "usage": {                       // 使用量统计
    "prompt_tokens": 19,
    "completion_tokens": 10,
    "total_tokens": 29,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "audio_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "service_tier": "default",       // 实际使用的服务等级
  "system_fingerprint": "string"   // 后端配置指纹
}
```

---

## 流式响应 (Streaming SSE)

当 `stream: true` 时，响应通过 Server-Sent Events 返回。

### SSE Chunk 结构

```json
// data: 行格式
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1741569952,
  "model": "gpt-5.4",
  "choices": [
    {
      "index": 0,
      "delta": {                    // 增量内容
        "role": "assistant",        // 仅第一个 chunk
        "content": "string",        // 文本增量
        "reasoning_content": "string", // 推理内容增量 (DeepSeek 等模型)
        "tool_calls": [             // 工具调用增量
          {
            "index": 0,
            "id": "string",
            "type": "function",
            "function": {
              "name": "string",
              "arguments": "string"
            }
          }
        ],
        "refusal": "string"
      },
      "logprobs": null,
      "finish_reason": "stop | null"  // 仅在最后一个 chunk 中有值
    }
  ],
  "usage": { ... },                // 仅在 stream_options.include_usage 时出现
  "system_fingerprint": "string"
}
```

流结束标志: `data: [DONE]`

---

## 示例

### 请求
```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-5.4",
    "messages": [
      {
        "role": "developer",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user",
        "content": "Hello!"
      }
    ]
  }'
```

### 响应
```json
{
  "id": "chatcmpl-B9MBs8CjcvOU2jLn4n570S5qMJKcT",
  "object": "chat.completion",
  "created": 1741569952,
  "model": "gpt-5.4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I assist you today?",
        "refusal": null,
        "annotations": []
      },
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 19,
    "completion_tokens": 10,
    "total_tokens": 29,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "audio_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "service_tier": "default"
}
```
