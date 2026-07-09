# Responses API vs Chat Completions API — 数据格式对比

> 基于 OpenAI 官方文档 (`developers.openai.com`)，与 codex-bridge 翻译实现相关

## 一、请求体对比

### 核心结构差异

| 维度 | Chat Completions | Responses |
|------|-----------------|-----------|
| **端点** | `POST /v1/chat/completions` | `POST /v1/responses` |
| **历史消息** | `messages: [...]` (数组) | `input: "..."` 或 `input: [{type, ...}]` (字符串或类型化数组) |
| **系统指令** | 作为 `messages` 中的 `role: "developer"/"system"` 消息 | 顶层 `instructions` 参数 |
| **多轮对话** | 手动拼接完整 `messages` 历史 | `previous_response_id` 或 `conversation` |
| **文本格式** | `response_format: { type: "json_object" }` | `text: { format: { type: "json_schema" } }` |
| **推理配置** | `reasoning_effort: "medium"` (单字段) | `reasoning: { effort, summary, context }` (对象) |

### 参数命名差异

| Chat Completions | Responses | 说明 |
|-----------------|-----------|------|
| `max_completion_tokens` | `max_output_tokens` | token 上限 |
| `response_format` | `text.format` | 输出格式 |
| `reasoning_effort` | `reasoning.effort` | 推理力度 |
| `messages` | `input` | 输入内容 |
| 无 | `previous_response_id` | 多轮引用 |
| 无 | `conversation` | 对话管理 |
| 无 | `background` | 后台运行 |
| 无 | `max_tool_calls` | 工具调用上限 |

### codex-bridge 翻译要点

在 `src/translate.py` 中的关键翻译：

1. **`input` → `messages`**: 类型化 input items 转为 role 化 messages
2. **`instructions` → system message**: 顶层 instructions 注入 messages[0] 作为 system role
3. **`function_call` → `tool_calls`**: type=function_call 的 input item → assistant message 的 tool_calls 数组
4. **`function_call_output` → tool role message**: 转为 `{ role: "tool", tool_call_id, content }`
5. **`reasoning` items**: 跳过，但将其 reasoning_content 附着到相邻 assistant message 上
6. **`developer` role → `system` role**: 因为 Chat API 的 developer role 模型兼容性不一

---

## 二、响应体对比

### 核心结构差异

| 维度 | Chat Completions | Responses |
|------|-----------------|-----------|
| **object** | `"chat.completion"` | `"response"` |
| **ID 前缀** | `chatcmpl-xxx` | `resp_xxx` |
| **时间戳** | `created` (Unix) | `created_at` (Unix) |
| **状态** | 无 | `status: "completed" \| "in_progress" \| "incomplete" \| "failed"` |
| **完成时间** | 无 | `completed_at` |
| **输出容器** | `choices[]` 数组 | `output[]` 数组 |
| **文本内容** | `choices[0].message.content` (字符串或数组) | `output[].content[]` 类型化数组 |
| **推理内容** | `choices[0].message.reasoning_content` (DeepSeek 扩展) | `output[]` 中的 `type: "reasoning"` item (官方支持) |
| **工具调用** | `choices[0].message.tool_calls[]` | `output[]` 中的 `type: "function_call"` item |
| **停止原因** | `choices[0].finish_reason` | 内嵌在 output items 的 status 中 |

### 响应结构对比图

```
Chat Completions:                    Responses:
{                                    {
  id: "chatcmpl-xxx",                  id: "resp_xxx",
  object: "chat.completion",           object: "response",
  created: 1741569952,                 created_at: 1741476542,
  model: "gpt-5.4",                    status: "completed",
  choices: [                           completed_at: 1741476543,
    {                                  model: "gpt-5.4",
      index: 0,                        output: [
      message: {                         {
        role: "assistant",                 type: "message",
        content: "text...",                id: "msg_xxx",
        tool_calls: [...]                  role: "assistant",
      },                                   content: [
      finish_reason: "stop"                  {
    }                                          type: "output_text",
  ],                                           text: "text...",
  usage: { ... }                             }
}                                           ]
                                          },
                                          {
                                            type: "reasoning",
                                            content: [...]
                                          },
                                          {
                                            type: "function_call",
                                            call_id: "...",
                                            name: "...",
                                            arguments: "..."
                                          }
                                        ],
                                        usage: { ... }
                                      }
```

### codex-bridge 翻译要点

在 `src/sse.py` 和 `src/server.py` 中的关键翻译：

1. **`choices[0].message.content` → `output[].content[].output_text`**: 
   - 非流式: `build_non_stream_response()` 组装 output 数组
   - 流式: `SseTranslator` 发出 `response.output_text.delta` 事件

2. **`choices[0].message.reasoning_content` → `output[].type: "reasoning"`**:
   - 流式: 发出 `response.reasoning_text.delta` 事件
   - 非流式: 组装独立的 reasoning output item

3. **`choices[0].message.tool_calls[]` → `output[].type: "function_call"`**:
   - 流式: 发出 `response.function_call_arguments.delta` 事件
   - item ID 加 `fc_` 前缀

4. **`choices[0].finish_reason` → 各 item status + `response.completed`**:
   - 每个 output item 发出 `response.output_item.done`
   - 最后发出 `response.completed`

---

## 三、流式 SSE 对比

| 维度 | Chat Completions SSE | Responses SSE |
|------|---------------------|---------------|
| **chunk 类型** | `object: "chat.completion.chunk"` | 多种 `type` 事件名 |
| **内容模型** | `delta` 增量模型 | 事件驱动模型 |
| **文本增量** | `choices[0].delta.content` | `response.output_text.delta` 事件 |
| **推理增量** | `choices[0].delta.reasoning_content` (非标) | `response.reasoning_text.delta` 事件 (官方) |
| **工具调用增量** | `choices[0].delta.tool_calls[]` | `response.function_call_arguments.delta` 事件 |
| **首 chunk** | delta 中带 `role: "assistant"` | 先发 `response.created`，再发 `response.in_progress` |
| **末 chunk** | `finish_reason` 设值 | 先发各 item 的 `done` 事件，再发 `response.completed` |
| **结束标志** | `data: [DONE]` | `event: done\ndata: [DONE]` |

### SSE 事件流对比

```
Chat Completions:           Responses:
data: {delta:{role}}    →   event: response.created
data: {delta:{content}} →   event: response.output_item.added
                             event: response.content_part.added
                             event: response.output_text.delta
data: {delta:{content}} →   event: response.output_text.delta
...                          ...
data: {finish_reason}   →   event: response.content_part.done
                             event: response.output_text.done
                             event: response.output_item.done
                             event: response.completed
data: [DONE]            →   event: done
                             data: [DONE]
```

---

## 四、工具调用对比

### 请求中的工具定义

```json
// Chat Completions
{
  "tools": [{
    "type": "function",
    "function": { "name": "x", "description": "y", "parameters": {} }
  }]
}

// Responses — 基本函数工具，格式相同
{
  "tools": [{
    "type": "function",
    "name": "x",
    "description": "y",
    "parameters": {}
  }]
}
// Responses 还支持内置工具:
// { "type": "web_search" }, { "type": "file_search" }, { "type": "code_interpreter" }
```

### 响应中的工具调用

```json
// Chat Completions — 嵌入在 assistant message 中
{ "role": "assistant", "tool_calls": [{ "id": "x", "function": { "name": "y", "arguments": "{}" } }] }

// Responses — 独立的 output item
{ "type": "function_call", "call_id": "x", "name": "y", "arguments": "{}" }
```

### 工具调用结果

```json
// Chat Completions — tool role message
{ "role": "tool", "tool_call_id": "x", "content": "result" }

// Responses — function_call_output input item
{ "type": "function_call_output", "call_id": "x", "output": "result" }
```

---

## 五、对 codex-bridge 项目的意义

codex-bridge 将 Codex CLI（使用 Responses API）连接到第三方模型（只支持 Chat Completions API），所以核心工作是翻译这些差异：

| 翻译方向 | 文件 | 关键挑战 |
|---------|------|----------|
| `input` → `messages` | `translate.py` | 类型化 items 需要拆解重组为 role-based messages |
| `instructions` → system msg | `server.py:78-83` | 注入身份声明，防止模型误认自己 |
| SSE 输出翻译 | `sse.py` | delta 模型 → 事件驱动模型，需维护状态机 |
| reasoning 恢复 | `recover.py` | DeepSeek 多轮 tool-call 丢失 reasoning_content |
| 非流式输出翻译 | `server.py:109-156` | choices[] → output[] 重组 |
