# codex-bridge

Zero-config bridge for [Codex CLI](https://github.com/openai/codex) — prefixes your model name with `-cb-` and automatically routes through any OpenAI-compatible API.

**No configuration files. No API keys. No setup.** Just run it and prefix your model.

Works great alongside [cc-switch](https://github.com/farion1231/cc-switch) for API key management — let cc-switch manage your provider keys, let codex-bridge handle the protocol translation.

## Quick Start

### 1. Start the bridge

```bash
git clone https://github.com/argszero/codex-bridge.git
cd codex-bridge
./start.sh
```

Requires Python ≥ 3.11. Uses [uv](https://docs.astral.sh/uv/).

### 2. Activate with a prefix

Edit `~/.codex/config.toml` — add `-cb-` to your model name:

```toml
model = "-cb-deepseek-v4-pro"
```

The watcher detects this within seconds, backs up your config, and rewrites it:

```toml
model = "deepseek-v4-pro"
[model_providers.custom]
base_url = "http://localhost:10110/api.deepseek.com"
```

Done. Open a new terminal and use Codex.

### 3. Deactivate

Remove the `-cb-` prefix. Restore your original `base_url` manually (your backup is at `~/.codex/config.toml.cb.bak`).

## Provider Examples

The watcher reads your existing `base_url` to discover the upstream API, so it works with whatever provider config you already have — cc-switch presets, manual config, or anything else. Just add `-cb-` to the model name.

### Kimi (Moonshot)

**Before** — your `~/.codex/config.toml` (configured via cc-switch Kimi preset or manually):

```toml
model_provider = "custom"
model = "kimi-k2.7-code"

[model_providers.custom]
name = "Kimi"
base_url = "https://api.moonshot.cn/v1"
api_key = "sk-..."
```

**Step 1** — add `-cb-` prefix:

```toml
model = "-cb-kimi-k2.7-code"   # ← add the prefix
```

**Step 2** — watcher auto-rewrites (seconds later):

```toml
model = "kimi-k2.7-code"
[model_providers.custom]
base_url = "http://localhost:10110/api.moonshot.cn/v1"
api_key = "sk-..."              # ← key preserved, forwarded by bridge
```

**Step 3** — restart Codex, done.

### DeepSeek

**Before:**

```toml
model_provider = "custom"
model = "deepseek-v4-pro"

[model_providers.custom]
base_url = "https://api.deepseek.com"
api_key = "sk-..."
```

**Add prefix** → watcher rewrites to:

```toml
model = "deepseek-v4-pro"
[model_providers.custom]
base_url = "http://localhost:10110/api.deepseek.com"
api_key = "sk-..."
```

### Alibaba DashScope (Qwen)

**Before:**

```toml
model_provider = "custom"
model = "qwen3-coder-plus"

[model_providers.custom]
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "sk-..."
```

**Add prefix** → watcher rewrites to:

```toml
model = "qwen3-coder-plus"
[model_providers.custom]
base_url = "http://localhost:10110/dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "sk-..."
```

### Groq

**Before:**

```toml
model_provider = "custom"
model = "qwen-qwq-32b"

[model_providers.custom]
base_url = "https://api.groq.com/openai/v1"
api_key = "gsk_..."
```

**Add prefix** → watcher rewrites to:

```toml
model = "qwen-qwq-32b"
[model_providers.custom]
base_url = "http://localhost:10110/api.groq.com/openai/v1"
api_key = "gsk_..."
```

### Ollama (local)

**Before:**

```toml
model_provider = "custom"
model = "qwen3:32b"

[model_providers.custom]
base_url = "http://localhost:11434/v1"
api_key = "ollama"
```

**Add prefix** → watcher rewrites to:

```toml
model = "qwen3:32b"
[model_providers.custom]
base_url = "http://localhost:10110/localhost:11434/v1"
api_key = "ollama"
```

> **How cc-switch fits in:** Use cc-switch to manage API keys and switch between providers with a GUI. cc-switch writes the `model_providers` section in `config.toml`. Then add `-cb-` to the model name, and codex-bridge picks up the upstream from cc-switch's config and handles the protocol translation — zero additional setup.

## How It Works

```
Codex CLI ──▶ ~/.codex/config.toml ──▶ bridge :10110 ──▶ Upstream API
                 ▲                             │
                 │   watcher detects -cb-      │  Responses → Chat
                 │   rewrites config           │  forwards client key
                 └─────────────────────────────┘
```

- **Watcher** polls `~/.codex/config.toml`, detects `-cb-` prefix, reads the existing `base_url` to discover the upstream host, then rewrites `base_url` to route through the bridge
- **Bridge** receives requests, extracts upstream from URL path, forwards with client's API key

### Request path encoding

The original upstream URL is encoded into the rewritten `base_url`:

| Original base_url | Rewritten |
|---|---|
| `https://api.deepseek.com` | `http://localhost:10110/api.deepseek.com` |
| `https://api.moonshot.cn/v1` | `http://localhost:10110/api.moonshot.cn/v1` |
| `https://dashscope.aliyuncs.com/compatible-mode/v1` | `http://localhost:10110/dashscope.aliyuncs.com/compatible-mode/v1` |
| `https://api.groq.com/openai/v1` | `http://localhost:10110/api.groq.com/openai/v1` |
| `http://localhost:11434/v1` (Ollama) | `http://localhost:10110/localhost:11434/v1` |

No state files, no side channels — the bridge knows where to forward from the URL alone.

## CLI Options

```bash
./start.sh --port 10110 --multimodal
```

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `10110` | Listen port |
| `--poll-interval` | `5` | Config poll interval (seconds) |
| `--timeout` | `30` | Upstream API timeout (minutes) |
| `--multimodal` | auto | Force-enable image support (auto-detected from model name by default) |

All flags are optional. Zero config needed.

## Supported Providers

Any provider with an **OpenAI-compatible Chat Completions API**:

- [DeepSeek](https://platform.deepseek.com/)
- [Moonshot (Kimi)](https://platform.moonshot.cn/)
- [Alibaba DashScope (Qwen)](https://dashscope.aliyun.com/)
- [Groq](https://console.groq.com/)
- [Together AI](https://api.together.xyz/)
- [Ollama](https://ollama.com/) (local)
- [vLLM](https://docs.vllm.ai/) (local)

## Protocol Translation

**Request (Responses → Chat Completions)**

| Responses API | Chat Completions |
|---|---|
| `input_text` / `output_text` | message `content` |
| `function_call` | assistant `tool_calls` |
| `function_call_output` | `tool` role message |
| `reasoning` | skipped; rc on adjacent message |
| `developer` role | `system` role |
| `instructions` | system message + identity injection |
| `tools` / `tool_choice` / `thinking` | translated |

**Response (Chat Completions SSE → Responses SSE)**

| Chat SSE | Responses SSE |
|---|---|
| First delta | `response.created` + `response.in_progress` |
| `delta.content` | `response.output_text.delta` / `done` |
| `delta.reasoning_content` | `response.reasoning_text.delta` / `done` |
| `delta.tool_calls` | `response.function_call_arguments.delta` / `done` |
| Stream end | `response.output_item.done` × N + `response.completed` |

## Files

| File | Description |
|------|-------------|
| `src/main.py` | Entry point — argparse CLI, starts watcher + server |
| `src/watcher.py` | Config poller — detects `-cb-`, backups & rewrites config |
| `src/server.py` | HTTP proxy — parses upstream from path, forwards requests |
| `src/translate.py` | Input translation (Responses → Chat) |
| `src/sse.py` | SSE output translation (Chat → Responses) |
| `src/recover.py` | reasoning_content recovery |
| `src/log.py` | Colored logging |

## Acknowledgments

Inspired by [codex-deepseek](https://github.com/yangfei4913438/codex-deepseek) — the original project that pioneered Responses ↔ Chat Completions protocol translation for Codex CLI. codex-bridge builds on that idea with a zero-config approach: no need to edit config files when switching models, just prefix your model name with `-cb-` and the watcher handles the rest.

## License

MIT
