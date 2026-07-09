# codex-bridge 翻译分析报告

对照 OpenAI Responses API 与 Chat Completions API 官方文档，逐项审查代码翻译质量。

每个问题标注严重程度：
- 🔴 **错误** — 会导致功能异常、数据错乱或请求失败
- 🟡 **信息丢失** — 部分数据被丢弃，但不导致崩溃
- 🟢 **可优化** — 功能正常，但有更好做法

---

## 一、请求翻译 (`translate.py` + `server.py:build_chat_body`)

### 1.1 `input` → `messages` 转换

#### ✅ 正确处理的部分

| 功能 | 代码位置 | 状态 |
|------|----------|------|
| 字符串 input → user message | `translate.py:77-78` | ✅ |
| dict input → 提取 content 为 user message | `translate.py:79-82` | ✅ |
| `role: "developer"` → `role: "system"` | `translate.py:145` | ✅ 第三方 API 兼容性好 |
| `function_call` → assistant tool_calls | `translate.py:90-118` | ✅ |
| `function_call_output` → tool role message | `translate.py:121-132` | ✅ |
| `reasoning` → 跳过但保留 rc 到相邻 msg | `translate.py:135-141` | ✅ |
| 多模态 image → `image_url` 格式 | `translate.py:28-58` | ✅ |
| base64 source 图片转换 | `translate.py:33-40` | ✅ |
| 无 image 时添加提示文本 | `translate.py:172-183` | ✅ |
| `extract_text` 处理多种 content 格式 | `translate.py:6-25` | ✅ |

#### 🔴 错误 — `function_call` status: "incomplete" 仍然作为完整 tool_call 发送

**位置**: `translate.py:111-115`

```python
if item.get("status") == "incomplete":
    log.warn("function_call status incomplete: " + ...)
```

问题：只打了 warning，但 `incomplete` 的 function_call 被正常加入 tool_calls 数组。Chat API 没有 "incomplete" 概念，上游模型会收到一个参数可能不完整的工具调用。这可能导致：
- 模型尝试执行不完整的函数调用
- 参数缺失导致 JSON 解析失败

**建议**: 跳过 `status == "incomplete"` 的 function_call，或将其 arguments 设为空。

#### 🔴 错误 — `function_call_output` status: "incomplete" 未处理

**位置**: `translate.py:127-131`

同样只打 warning 但仍传递。上游模型会收到可能不完整的工具执行结果。

**建议**: 跳过或标记不完整的 function_call_output。

#### 🔴 错误 — 多 session 并发时 reasoning 恢复会错乱

**位置**: `recover.py:9,40-42`

```python
_queue: list[str] = []          # 全局共享队列
def session_key(body: dict) -> str:
    return "g"                   # 永远返回相同 key
```

`_queue` 是模块级全局变量，`session_key()` 永远返回 `"g"`。如果多个 Codex 实例同时使用 bridge（多线程），session A 的 reasoning 可能被恢复到 session B 的消息中。

**建议**: 至少用 `threading.local()` 隔离，或基于请求中的 `previous_response_id` 做真正的 session 隔离。

#### 🟡 信息丢失 — `type: "message"` input item 的 `id` 和 `status` 字段丢失

**位置**: `translate.py:197-201`

```python
if item.get("type") == "message":
    text_content = extract_text(item.get("content"))
    if text_content:
        messages.append({"role": "user", "content": text_content})
```

Responses API 的 `message` 类型 item 有 `id`、`status`、`phase` 等字段。当 role 为 `assistant` 且标记为历史消息时，这些信息被丢弃。虽然影响较小，但在多轮对话中如果 Codex 传入了之前的助手消息，会丢失一些元数据。

#### 🟡 信息丢失 — File 和 Audio 输入完全丢弃

**位置**: `translate.py:156-159`

```python
elif t == "input_file":
    stats["skipped"]["file"] += 1
elif t == "input_audio":
    stats["skipped"]["audio"] += 1
```

Responses API 支持文件输入（`input_file` 含 `file_data` 或 `file_id`）和音频输入（`input_audio`）。这些被完全丢弃，仅在统计中记录。如果 Codex 上传了文件内容，模型将看不到。

**建议**: 至少为 `input_file` 生成一段说明文本（如同 image 的处理方式），告知模型有文件被跳过。

#### 🟡 信息丢失 — 内置工具被静默丢弃

**位置**: `translate.py:227-248` (`translate_tools`)

```python
for t in raw_tools:
    name = t.get("name") or t.get("function", {}).get("name")
    if not name:
        continue  # 内置工具没有 name 字段，被静默跳过
```

Responses API 支持 `web_search`、`file_search`、`code_interpreter`、`mcp` 等内置工具。这些工具没有 `name` 字段，被 `translate_tools` 静默跳过，没有任何警告。

**影响**: 如果 Codex 尝试使用 `web_search` 工具，bridge 不会报错但工具不可用，模型会"假装搜索"。

**建议**: 至少打印一条 warning，告知用户不支持的内置工具类型。

#### 🟢 可优化 — `text.format` 未映射到 `response_format`

**位置**: `server.py:build_chat_body`

Responses API 的 `text: { format: { type: "json_schema", schema: ... } }` 对应 Chat API 的 `response_format: { type: "json_schema", json_schema: ... }`。当前代码完全没处理 `text` 参数。

```python
# 当前: 未翻译
# 建议添加:
if body.get("text", {}).get("format", {}).get("type") == "json_schema":
    chat_body["response_format"] = {
        "type": "json_schema",
        "json_schema": body["text"]["format"]
    }
elif body.get("text", {}).get("format", {}).get("type") == "json_object":
    chat_body["response_format"] = {"type": "json_object"}
```

#### 🟢 可优化 — 多个 Chat API 参数未透传

以下参数在 Responses API 和 Chat Completions API 中**名称和含义完全相同**，但 `build_chat_body` 没有透传：

| Responses 参数 | Chat 参数 | 影响 |
|---------------|-----------|------|
| `store` | `store` | 缓存/存储策略丢失 |
| `safety_identifier` | `safety_identifier` | 用户安全标识丢失 |
| `metadata` | `metadata` | 元数据丢失 |
| `service_tier` | `service_tier` | 服务等级丢失 |
| `parallel_tool_calls` | `parallel_tool_calls` | 并行工具调用设置丢失 |
| `top_logprobs` | `top_logprobs` | logprobs 设置丢失 |
| `prompt_cache_key` | `prompt_cache_key` | 缓存优化 key 丢失 |
| `prompt_cache_retention` | `prompt_cache_retention` | 缓存保留策略丢失 |
| `frequency_penalty` | `frequency_penalty` | 频率惩罚丢失 |
| `presence_penalty` | `presence_penalty` | 存在惩罚丢失 |
| `stop` | `stop` | 停止序列丢失 |
| `n` | `n` | 多选项生成丢失 |
| `prediction` | `prediction` | 预测内容丢失 |

**建议**: 添加一个通用透传循环，对名称相同的参数自动转发。

---

## 二、响应翻译 — 非流式 (`server.py:build_non_stream_response`)

### 2.1 ✅ 正确处理的部分

| 功能 | 状态 |
|------|------|
| `choices[0].message.content` → output_text item | ✅ |
| `choices[0].message.reasoning_content` → reasoning item | ✅ |
| `choices[0].message.tool_calls[]` → function_call items | ✅ |
| `usage` 数据格式转换 (`prompt_tokens` → `input_tokens`) | ✅ |

### 2.2 发现的问题

#### 🔴 错误 — `refusal` 字段未检查，安全拒绝返回空响应

**位置**: `server.py:122-131`

```python
if msg.get("content"):
    output.append({...})  # 只有 content 非空才添加
```

Chat API 的安全拒绝放在 `message.refusal` 字段中，此时 `message.content` 为 null。代码只检查 `content`，导致模型因安全原因拒绝时，bridge 返回一个**空的 output 数组**，Codex 无法得知发生了什么。

```json
// 上游实际返回:
{ "message": { "content": null, "refusal": "I cannot help with that." } }

// bridge 翻译后:
{ "output": [] }  // 空！拒绝信息丢失
```

**建议**: 检查 `refusal` 字段并生成对应的 output_text 或错误信息。

#### 🔴 错误 — 多 choices (n > 1) 只取第一个

**位置**: `server.py:111`

```python
msg = (completion.get("choices") or [{}])[0].get("message", {})
```

Responses API 不支持 n>1，但如果上游返回多个 choices（某些 API 默认行为），其余 choices 被丢弃。当 Codex 请求 `n > 1` 时，只能拿到一个结果。

**建议**: 至少对 `n > 1` 的情况打 warning。

#### 🟡 信息丢失 — `finish_reason` 未被翻译

Chat API 的 `finish_reason`（`stop`/`length`/`tool_calls`/`content_filter`）在 Responses API 中没有直接对应字段，但 `incomplete_details` 可以承载部分语义。当前完全丢弃。

**影响**: 当 `finish_reason == "length"` 时，Codex 无法得知响应被截断。

#### 🟡 信息丢失 — `annotations` 未传播

**位置**: `server.py:128`

```python
"annotations": []  # 硬编码为空
```

Chat API 的 message 可能有 `annotations` 字段（如 URL 引用）。当前总是返回空数组。

#### 🟡 信息丢失 — 旧版 `function_call` 未处理

**位置**: `server.py:132-141`

代码只检查 `msg.get("tool_calls")`，但 Chat API 的旧版响应可能包含 `function_call`（单数，已弃用）而不是 `tool_calls`。使用较老模型时，工具调用会丢失。

#### 🟢 可优化 — Response 对象缺少多个字段

`build_non_stream_response` 返回的 response 对象缺少：
- `created_at` — 可用当前时间戳填充
- `completed_at` — 可用当前时间戳填充
- `incomplete_details` — 可从 `finish_reason` 推导
- `parallel_tool_calls` — 可从请求回显
- `temperature` / `top_p` / `tools` / `tool_choice` — 可从请求回显

**重要性**: 低。这些大多是 metadata/echo 字段，Codex 大概率不依赖。

---

## 三、响应翻译 — 流式 (`sse.py`)

### 3.1 ✅ 正确处理的部分

| 功能 | 状态 |
|------|------|
| SSE 生命周期事件 (`response.created` → `in_progress` → `completed`) | ✅ |
| 文本增量 (`delta.content` → `output_text.delta`) | ✅ |
| 推理增量 (`delta.reasoning_content` → `reasoning_text.delta`) | ✅ |
| 函数调用增量 (`delta.tool_calls` → `function_call_arguments.delta`) | ✅ |
| 输出 item 管理 (added/done 事件对) | ✅ |
| 流结束 `[DONE]` 标记 | ✅ |
| 错误事件翻译 | ✅ |

### 3.2 发现的问题

#### 🔴 错误 — Streaming 中 `refusal` delta 未处理

**位置**: `sse.py:38-203` (`feed` 方法)

Chat SSE 的 delta 可能包含 `refusal` 字段（安全拒绝时的增量文本）。`SseTranslator.feed()` 只检查 `delta.get("content")`、`delta.get("reasoning_content")`、`delta.get("tool_calls")`，完全不处理 `refusal`。

当模型触发安全拒绝时：
- stream 中只有 `refusal` 增量，没有 `content` 增量
- bridge 不会发出任何 `output_text.delta` 事件
- Codex 收到一个空的 response（无 output items）
- 用户看到空白或超时

**影响**: 安全过滤场景下用户看不到任何错误信息。

#### 🔴 错误 — Streaming 中旧版 `function_call` delta 未处理

**位置**: `sse.py:152-203`

```python
if delta.get("tool_calls"):
    for tc in delta["tool_calls"]:
        ...
```

Chat SSE delta 可能包含 `function_call`（旧版，单数，含 `name` 和 `arguments`）而不是 `tool_calls`。使用较老模型或某些第三方 API 时，工具调用在流式模式下完全丢失。

#### 🟡 信息丢失 — `response.created` 缺少 `created_at` 时间戳

**位置**: `sse.py:419-445` (`_ensure_started`)

```python
"response": {
    "id": self.response_id,
    "object": "response",
    "status": "in_progress",
    "model": self.model,
    "output": [],
    # 缺少 "created_at"
}
```

官方 Response 对象包含 `created_at` 字段。虽然 Codex 可能不强制要求，但为保持兼容应添加。

#### 🟡 信息丢失 — Streaming 中 `delta.audio` 未处理

Chat API 的 `modalities: ["audio"]` 模式下，delta 可能包含 `audio` 数据。未处理。

#### 🟢 可优化 — `done()` 中 tool call snapshot 有 O(n²) 嵌套循环

**位置**: `sse.py:364-374`

```python
elif o["type"] == "function_call":
    for c in self.tool_calls.values():
        if f"fc_{c['id']}" == o["itemId"]:
            out_snapshot.append({...})
```

对每个 function_call 类型的 output item，都遍历全部 tool_calls 来查找匹配。可以用 dict 索引优化：

```python
# 建议: 预建索引
tc_by_fc = {f"fc_{c['id']}": c for c in self.tool_calls.values()}
# 然后 O(1) 查找
```

#### 🟢 可优化 — streaming 中 buffer 处理

**位置**: `server.py:424-460`

stream 读取的 buffer 处理手动拼接 `buf`、按 `\n` 分割、处理跨 chunk 的不完整行。功能正确但代码较长。可考虑用 `io.TextIOWrapper` 简化。

---

## 四、其他问题

### 4.1 服务器层

#### 🟡 信息丢失 — Header 转发只处理 `x-` 和 `openai-` 前缀

**位置**: `server.py:189-196`

```python
if kl.startswith("x-") or kl.startswith("openai-"):
    headers[key] = value
```

某些合法的 HTTP headers（如 `Accept-Language`、`User-Agent`）可能影响上游 API 行为，但被选择性丢弃。Chat API 的某些功能（如地域相关内容）可能依赖这些 headers。

#### 🟢 可优化 — `/models` 端点返回硬编码数据

**位置**: `server.py:276-286`

```json
{ "id": "codex-bridge", "object": "model" }
```

如果 Codex 查询 `/models` 来验证模型可用性，它只能看到一个假的 `codex-bridge` 模型。更完整的做法是代理到上游或返回实际模型名。

### 4.2 Watcher

#### 🟢 可优化 — 配置重写只改 `[model_providers.*]` 下的 `base_url`

**位置**: `watcher.py:112-126`

```python
if re.match(r'^\s*\[model_providers\.', line):
    in_provider = True
elif in_provider and re.match(r'^\s*base_url\s*=', line):
    new_lines.append(f'base_url = "{bridge_url}"\n')
```

这只修改 `[model_providers.*]` section 下的 base_url。如果 TOML 中 `base_url` 在别处定义（如 inline table），不会被修改。

---

## 五、问题汇总

### 🔴 错误 (5 个)

| # | 位置 | 问题 |
|---|------|------|
| 1 | `translate.py:111-115` | `function_call` status: "incomplete" 的 partial arguments 被当作完整 tool_call 发送 |
| 2 | `translate.py:127-131` | `function_call_output` status: "incomplete" 的 partial 结果被传出 |
| 3 | `recover.py:9,40-42` | 全局 `_queue` + `session_key() == "g"` 导致多 session reasoning 错乱 |
| 4 | `server.py:122-131` | `refusal` 字段未检查，安全拒绝时返回空白输出（非流式） |
| 5 | `sse.py:38-203` | Streaming delta 中 `refusal` 未处理，安全拒绝时静默（流式） |

### 🟡 信息丢失 (10 个)

| # | 位置 | 问题 |
|---|------|------|
| 6 | `translate.py:197-201` | `type: "message"` item 的 id/status/phase 丢失 |
| 7 | `translate.py:156-159` | File/Audio 输入被完全丢弃，无提示 |
| 8 | `translate.py:227-248` | 内置工具 (web_search 等) 被静默丢弃，无 warning |
| 9 | `server.py:111` | 多 choices (n>1) 只取第一个 |
| 10 | `server.py:111` | `finish_reason` 未翻译 |
| 11 | `server.py:128` | `annotations` 总是空数组 |
| 12 | `server.py:132-141` | 旧版 `function_call` (非 tool_calls) 未处理（非流式） |
| 13 | `sse.py:152-203` | 旧版 `function_call` delta 未处理（流式） |
| 14 | `sse.py:419-445` | `response.created` 缺少 `created_at` |
| 15 | `sse.py` / `server.py` | `delta.audio` 未处理 |

### 🟢 可优化 (8 个)

| # | 位置 | 问题 |
|---|------|------|
| 16 | `server.py:build_chat_body` | `text.format` → `response_format` 映射缺失 |
| 17 | `server.py:build_chat_body` | 13 个同名参数未透传 (store, metadata 等) |
| 18 | `sse.py:364-374` | O(n²) tool call snapshot 循环 |
| 19 | `server.py:424-460` | stream buffer 处理可用 io 库简化 |
| 20 | `server.py:189-196` | Header 转发可更完整 |
| 21 | `server.py:276-286` | `/models` 端点返回假数据 |
| 22 | `watcher.py:112-126` | base_url 重写可能遗漏 inline table |
| 23 | `server.py:build_non_stream_response` | Response echo 字段不完整 |

---

## 六、修改优先级建议

**P0 — 立即修复**:
- #1, #2: incomplete status 处理 (可能导致错误 tool call)
- #3: reasoning session 隔离 (多 session 下数据错乱)
- #4, #5: refusal 处理 (安全场景下静默失败)

**P1 — 建议修复**:
- #7, #8: File/Audio/内置工具的降级提示
- #12, #13: 旧版 function_call 兼容

**P2 — 可以考虑**:
- #16, #17: 参数透传增强
- #18: 性能优化
- #6, #9, #10, #11, #14, #15: 字段补全
