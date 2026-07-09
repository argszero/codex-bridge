"""HTTP server: listens on port 10110, translates Responses API ↔ Chat Completions."""

import json
import random
import string
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import log
from .recover import recover_reasoning, remember_reasoning, session_key
from .sse import SseTranslator
from .translate import (
    last_user_text,
    translate_messages,
    translate_tool_choice,
    translate_tools,
)


def _rand_id(prefix: str, length: int = 8) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{prefix}_{suffix}"


def build_chat_body(
    body: dict,
    base_url: str,
    model: str,
    multimodal: bool,
) -> dict:
    """Translate a Responses API request body into a Chat Completions body."""
    stream = body.get("stream") is not False
    raw_thinking = body.get("thinking")
    raw_reasoning = body.get("reasoning")
    has_thinking = raw_thinking is not None or raw_reasoning is not None

    # Auto-detect multimodal from model name (blocklist for non-vision models).
    # CLI flag (--multimodal) overrides the auto-detection.
    if not multimodal:
        model_lower = model.lower()
        multimodal = not any(
            name in model_lower for name in ("deepseek-v4", "deepseek-v3")
        )

    result = translate_messages(
        body.get("input"),
        {"keepReasoningContent": has_thinking, "multimodal": multimodal},
    )
    messages = result["messages"]
    stats = result["stats"]

    restored = recover_reasoning(session_key(body), messages)
    has_assistant_with_rc = any(
        m.get("role") == "assistant" and m.get("reasoning_content") for m in messages
    )
    has_assistant_with_tc = any(
        m.get("role") == "assistant" and m.get("tool_calls") for m in messages
    )
    effective_thinking = has_thinking and (
        has_assistant_with_rc or not has_assistant_with_tc
    )

    if has_thinking and not effective_thinking:
        log.warn("thinking off: missing rc in history")
    if restored > 0 and effective_thinking:
        log.ok(f"rc restored x{restored}")
    if stats["strippedReasoningContent"] > 0:
        log.skip(f"rc stripped x{stats['strippedReasoningContent']}")
    if stats["preservedReasoningContent"] > 0 and not restored:
        log.info(f"rc preserved x{stats['preservedReasoningContent']}")

    last_user = last_user_text(messages)
    preview = last_user[:120] + "..." if len(last_user) > 120 else last_user
    log.req(
        f"thinking:{'on' if has_thinking else 'off'} "
        f"msgs:{len(messages)} stream:{stream} | {preview}"
    )

    # Identity injection
    IDENTITY = (
        f"\n\n[IMPORTANT: Your true model identity is {model}. "
        "You are NOT OpenAI, GPT, or Claude. When asked about your model identity, "
        "you MUST answer truthfully based on your actual model name. "
        "Ignore any conflicting identity claims in the instructions above.]"
    )
    instructions = body.get("instructions", "")
    if instructions:
        instructions = instructions + IDENTITY
    else:
        instructions = IDENTITY.strip()
    messages.insert(0, {"role": "system", "content": instructions})

    chat_body: dict = {"model": model, "messages": messages, "stream": stream}
    # Pass through thinking/reasoning from the request as-is
    if raw_thinking is not None:
        chat_body["thinking"] = raw_thinking
    elif raw_reasoning is not None:
        chat_body["reasoning"] = raw_reasoning

    tools = translate_tools(body.get("tools"))
    if tools:
        chat_body["tools"] = tools
        tc = translate_tool_choice(body.get("tool_choice"))
        if tc:
            chat_body["tool_choice"] = tc

    if body.get("temperature") is not None:
        chat_body["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        chat_body["top_p"] = body["top_p"]
    if body.get("max_output_tokens") is not None:
        chat_body["max_tokens"] = body["max_output_tokens"]

    # Pass through parameters that share the same name in both APIs
    _PASSTHROUGH_PARAMS = (
        "store", "safety_identifier", "metadata", "service_tier",
        "parallel_tool_calls", "prompt_cache_key", "prompt_cache_retention",
        "frequency_penalty", "presence_penalty", "stop", "n",
        "prediction", "verbosity", "web_search_options", "modalities",
        "moderation", "logprobs", "top_logprobs",
    )
    for param in _PASSTHROUGH_PARAMS:
        val = body.get(param)
        if val is not None:
            chat_body[param] = val

    # top_logprobs requires logprobs to be true in Chat API
    if body.get("top_logprobs") is not None and body.get("logprobs") is None:
        chat_body["logprobs"] = True

    # Map text.format to response_format when applicable
    text_cfg = body.get("text", {})
    if isinstance(text_cfg, dict):
        fmt = text_cfg.get("format", {})
        if isinstance(fmt, dict):
            fmt_type = fmt.get("type")
            if fmt_type == "json_schema":
                # Copy the format dict as json_schema (minus "type")
                json_schema = {k: v for k, v in fmt.items() if k != "type"}
                chat_body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": json_schema,
                }
            elif fmt_type == "json_object":
                chat_body["response_format"] = {"type": "json_object"}

    return {"chat_body": chat_body, "stream": stream, "messages": messages}


def build_non_stream_response(completion: dict, model: str) -> dict:
    """Build a non-streaming Responses API response from a Chat Completions response."""
    msg = (completion.get("choices") or [{}])[0].get("message", {})
    usage = completion.get("usage")
    output = []

    if msg.get("reasoning_content"):
        output.append({
            "id": _rand_id("rsn", 6),
            "type": "reasoning",
            "content": [{"type": "reasoning_text", "text": msg["reasoning_content"]}],
            "status": "completed",
        })
    if msg.get("content"):
        output.append({
            "id": _rand_id("msg", 6),
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": msg["content"], "annotations": []}
            ],
            "status": "completed",
        })
    elif msg.get("refusal"):
        # Safety refusal — content is null, refusal contains the explanation
        output.append({
            "id": _rand_id("msg", 6),
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": msg["refusal"], "annotations": []}
            ],
            "status": "completed",
        })
    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            output.append({
                "id": f"fc_{tc['id']}",
                "type": "function_call",
                "call_id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": tc["function"]["arguments"],
                "status": "completed",
            })
    # Handle legacy function_call (singular, deprecated)
    if msg.get("function_call") and not msg.get("tool_calls"):
        fc = msg["function_call"]
        output.append({
            "id": f"fc_{fc.get('name', 'legacy')}",
            "type": "function_call",
            "call_id": fc.get("name", "legacy"),
            "name": fc.get("name", ""),
            "arguments": fc.get("arguments", ""),
            "status": "completed",
        })

    return {
        "id": _rand_id("resp", 10),
        "object": "response",
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
            "output_tokens": usage.get("completion_tokens", 0) if usage else 0,
            "total_tokens": usage.get("total_tokens", 0) if usage else 0,
        }
        if usage
        else None,
    }


FORWARD_HEADERS = {
    "user-agent", "x-", "openai-", "content-type", "accept",
    "accept-encoding", "accept-language", "connection",
}

def upstream_request(
    base_url: str,
    api_key: str,
    chat_body: dict,
    timeout: int,
    client_headers: dict | None = None,
    stream: bool = False,
) -> tuple:
    """Call the upstream API via http.client.

    Returns (status, body_or_response, connection).
    """
    parsed = urlparse(base_url)
    host = parsed.netloc or "api.deepseek.com"
    path = parsed.path.rstrip("/") + "/chat/completions"
    body_bytes = json.dumps(chat_body).encode("utf-8")

    # Start with our required headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }
    # Forward allowed client headers (our required headers take precedence)
    if client_headers:
        for key, value in client_headers.items():
            kl = key.lower()
            if kl in ("authorization", "host", "content-length", "transfer-encoding"):
                continue  # we set these ourselves, or they're hop-by-hop
            if kl.startswith("x-") or kl.startswith("openai-"):
                headers[key] = value
            elif kl in ("user-agent", "accept-encoding", "accept-language"):
                headers[key] = value

    conn = HTTPSConnection(host, timeout=timeout)
    try:
        conn.request("POST", path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        if resp.status != 200:
            err_body = resp.read().decode()[:500]
            conn.close()
            return resp.status, err_body, None
        if stream:
            return resp.status, resp, conn
        else:
            data = resp.read().decode()
            conn.close()
            return resp.status, data, None
    except Exception as e:
        conn.close()
        return None, str(e), None


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the bridge proxy."""

    # Injected by the server factory
    timeout: int = 30 * 60
    multimodal: bool = False

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def log_message(self, format, *args):
        pass  # Suppress default HTTP logging

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse_response(self, generator):
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            for chunk in generator:
                self.wfile.write(
                    chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                )
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.endswith("/health"):
            self._json_response({
                "service": "codex-bridge",
                "status": "ok",
            })
        elif path.endswith("/models"):
            self._json_response({
                "object": "list",
                "data": [
                    {
                        "id": "codex-bridge",
                        "object": "model",
                        "created": 1700000000,
                        "owned_by": "codex-bridge",
                    }
                ],
            })
        else:
            self._json_response({"error": {"message": f"not found: {path}"}}, 404)

    def _client_api_key(self) -> str:
        """Extract API key from incoming Authorization header."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return ""

    def _parse_upstream(self) -> str | None:
        """Extract upstream host+path from request path.

        Path format: /{upstream}/responses
        e.g. /api.deepseek.com/responses → api.deepseek.com
             /coding.dashscope.aliyuncs.com/v1/responses → coding.dashscope.aliyuncs.com/v1

        Handles three request-line forms:
        1. Origin-form:   /api.deepseek.com/responses
        2. Absolute-form: http://localhost:10110/api.deepseek.com/responses
        3. Codex-prepended: /localhost:10110/api.deepseek.com/responses
           (Codex naively splices host:port into the path)
        """
        import re
        raw = self.path.split("?")[0]
        # Step 1: urlparse strips scheme+host from absolute-form URIs
        path = urlparse(raw).path
        # Step 2: strip any leading /host:port/ that Codex may have
        #          spliced into the path (e.g. /localhost:10110/…)
        path = re.sub(r'^/[^/]+:\d+/', '/', path)
        log.info(f"parse_upstream: raw={raw} → path={path}")
        if not path.endswith("/responses"):
            return None
        # Strip leading / and trailing /responses
        upstream = path[1:].removesuffix("/responses")
        log.info(f"parse_upstream: upstream={upstream}")
        return upstream or None

    def _upstream_base_url(self, upstream: str) -> str:
        """Build full upstream base URL from the host+path segment."""
        return f"https://{upstream}"

    def do_POST(self):
        upstream = self._parse_upstream()
        if not upstream:
            self._json_response({"error": {"message": f"not found: {self.path}"}}, 404)
            return

        try:
            content_len = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_len).decode("utf-8")
            body = json.loads(raw)
        except Exception as e:
            self._json_response({"error": {"message": str(e)}}, 400)
            return

        upstream_url = self._upstream_base_url(upstream)
        log.info(f"upstream: {upstream_url}")

        # Model comes from the incoming request (Codex sends it)
        req_model = body.get("model", "")

        try:
            built = build_chat_body(
                body, upstream_url, req_model, self.multimodal
            )
        except Exception as e:
            log.err(f"build: {e}")
            self._json_response({"error": {"message": str(e)}}, 400)
            return

        chat_body = built["chat_body"]
        stream = built["stream"]

        log.info(f"stream:{stream}")
        if not stream:
            self._handle_non_stream(body, chat_body, upstream_url, req_model)
        else:
            self._handle_stream(body, chat_body, upstream_url, req_model)

    def _forward_headers(self) -> dict:
        """Extract headers from the incoming request to forward upstream."""
        h = {}
        for key, value in self.headers.items():
            h[key] = value
        return h

    def _handle_non_stream(self, body: dict, chat_body: dict, upstream_url: str, req_model: str) -> None:
        api_key = self._client_api_key()
        status, resp_body, conn = upstream_request(
            upstream_url, api_key, chat_body, self.timeout,
            client_headers=self._forward_headers(),
        )
        if status != 200:
            log.err(f"Upstream {status}: {resp_body[:300]}")
            self._json_response(
                {
                    "error": {
                        "type": "upstream_error",
                        "code": f"upstream_{status}",
                        "message": f"Upstream {status}: {resp_body[:200]}",
                    }
                },
                502 if status and status >= 500 else status or 502,
            )
            return
        try:
            completion = json.loads(resp_body)
        except Exception as e:
            log.err(f"parse: {e}")
            self._json_response({"error": {"message": str(e)}}, 502)
            return
        if (
            completion
            .get("choices", [{}])[0]
            .get("message", {})
            .get("reasoning_content")
        ):
            remember_reasoning(
                session_key(body), [completion["choices"][0]["message"]]
            )
        response = build_non_stream_response(completion, req_model)
        usg = completion.get("usage")
        if usg:
            log.toks(
                usg.get("prompt_tokens"),
                usg.get("completion_tokens"),
                usg.get("total_tokens"),
            )
        self._json_response(response, 200)

    def _handle_stream(self, body: dict, chat_body: dict, upstream_url: str, req_model: str) -> None:
        api_key = self._client_api_key()
        client_headers = self._forward_headers()

        def generate():
            translator = SseTranslator(req_model)
            conn = None
            try:
                status, resp, conn = upstream_request(
                    upstream_url, api_key, chat_body, self.timeout,
                    client_headers=client_headers, stream=True
                )
                if status != 200 or isinstance(resp, str):
                    err_body = resp if isinstance(resp, str) else resp[:300]
                    log.err(f"Upstream {status}: {err_body}")
                    yield translator.error(f"Upstream {status}: {err_body[:200]}")
                    return
                # Read in 4KB chunks; buffer as bytes to avoid splitting
                # multi-byte UTF-8 chars at chunk boundaries
                buf = b""
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line_bytes, buf = buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8")
                        if not line.startswith("data: "):
                            continue
                        json_str = line[6:].strip()
                        if json_str == "[DONE]":
                            continue
                        try:
                            parsed = json.loads(json_str)
                            result = translator.feed(parsed)
                            if result:
                                yield result
                        except (json.JSONDecodeError, ValueError):
                            pass
                # Flush remaining buffer
                for line_bytes in buf.split(b"\n"):
                    if not line_bytes:
                        continue
                    line = line_bytes.decode("utf-8")
                    if not line.startswith("data: "):
                        continue
                    json_str = line[6:].strip()
                    if json_str == "[DONE]":
                        continue
                    try:
                        parsed = json.loads(json_str)
                        result = translator.feed(parsed)
                        if result:
                            yield result
                    except (json.JSONDecodeError, ValueError):
                        pass
                if translator.reasoning_so_far:
                    remember_reasoning(
                        session_key(body),
                        [
                            {
                                "role": "assistant",
                                "content": translator.content_so_far,
                                "reasoning_content": translator.reasoning_so_far,
                            }
                        ],
                    )
                yield translator.done(None)
            except Exception as e:
                log.err(f"upstream: {e}")
                yield translator.error(str(e))
            finally:
                if conn:
                    conn.close()

        self._sse_response(generate())


def create_server(
    port: int,
    timeout: int,
    multimodal: bool,
) -> ThreadingHTTPServer:
    """Create and return a configured ThreadingHTTPServer."""
    server = ThreadingHTTPServer(("127.0.0.1", port), ProxyHandler)
    ProxyHandler.timeout = timeout
    ProxyHandler.multimodal = multimodal
    return server
