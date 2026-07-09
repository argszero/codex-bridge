from typing import Any, Optional

from . import log


def extract_text(content: Any) -> str:
    """Extract plain text from various content formats."""
    if isinstance(content, str):
        return content
    if not content:
        return ""
    if not isinstance(content, list):
        if (
            isinstance(content, dict)
            and "type" in content
            and content.get("text") is not None
        ):
            return content["text"]
        return ""
    return "".join(
        p.get("text", "")
        for p in content
        if isinstance(p, dict)
        and p.get("type") in ("input_text", "output_text", "text", "reasoning_text")
    )


def _convert_image_url(part: dict) -> Optional[dict]:
    """Convert an image part to OpenAI vision format."""
    image_url = part.get("image_url")
    if image_url and isinstance(image_url, str):
        return {"type": "image_url", "image_url": {"url": image_url}}
    source = part.get("source")
    if isinstance(source, dict) and source.get("type") == "base64":
        mt = source.get("media_type", "image/jpeg")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mt};base64,{source.get('data', '')}"},
        }
    return None


def _build_content_parts(content_list: list) -> list[dict]:
    """Build multimodal content parts from a content list."""
    parts: list[dict] = []
    for p in content_list:
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t in ("input_text", "output_text", "text", "reasoning_text"):
            text = p.get("text", "")
            if text:
                parts.append({"type": "text", "text": text})
        elif t == "input_image":
            img = _convert_image_url(p)
            if img:
                parts.append(img)
    return parts


def translate_messages(input_data: Any, options: Optional[dict] = None) -> dict:
    """Translate Responses API input items into Chat Completions messages.

    Returns {"messages": [...], "stats": {...}}.
    """
    options = options or {}
    keep_reasoning_content = options.get("keepReasoningContent", False)
    multimodal = options.get("multimodal", False)
    messages: list[dict] = []
    stats = {
        "skipped": {"reasoning": 0, "image": 0, "file": 0, "audio": 0, "other": 0},
        "strippedReasoningContent": 0,
        "preservedReasoningContent": 0,
    }

    if not isinstance(input_data, list):
        if isinstance(input_data, str) and input_data.strip():
            messages.append({"role": "user", "content": input_data})
        elif isinstance(input_data, dict):
            text = extract_text(input_data.get("content"))
            if text:
                messages.append({"role": "user", "content": text})
        return {"messages": messages, "stats": stats}

    for item in input_data:
        if not item:
            continue

        # --- function_call ---
        if item.get("type") == "function_call":
            call_id = item.get("call_id") or item.get("id")
            if item.get("status") == "incomplete":
                log.warn(f"function_call skipped (status incomplete): {call_id}")
                continue
            last = (
                messages[-1]
                if messages and messages[-1].get("role") == "assistant"
                else None
            )
            target = (
                last if last is not None else {"role": "assistant", "tool_calls": []}
            )
            if last is None:
                messages.append(target)
            if "tool_calls" not in target:
                target["tool_calls"] = []
            target["tool_calls"].append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": item.get("name"),
                    "arguments": item.get("arguments"),
                },
            })
            if item.get("reasoning_content") and "reasoning_content" not in target:
                target["reasoning_content"] = item["reasoning_content"]
            continue

        # --- function_call_output ---
        if item.get("type") == "function_call_output":
            call_id = item.get("call_id") or item.get("id")
            if item.get("status") == "incomplete":
                log.warn(f"function_call_output skipped (status incomplete): {call_id}")
                continue
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": extract_text(item.get("output")),
            })
            continue

        # --- reasoning (skipped, but preserve rc on adjacent message) ---
        if item.get("type") == "reasoning":
            stats["skipped"]["reasoning"] += 1
            if item.get("reasoning_content"):
                last = messages[-1] if messages else None
                if last and "reasoning_content" not in last:
                    last["reasoning_content"] = item["reasoning_content"]
            continue

        # --- role-based items ---
        if "role" in item:
            role = "system" if item["role"] == "developer" else item["role"]
            text_content = extract_text(item.get("content"))

            skipped_images = 0
            skipped_files = 0
            skipped_audios = 0
            content_parts = None
            if isinstance(item.get("content"), list):
                for p in item["content"]:
                    t = p.get("type") if isinstance(p, dict) else None
                    if t == "input_image":
                        skipped_images += 1
                        stats["skipped"]["image"] += 1
                    elif t == "input_file":
                        skipped_files += 1
                        stats["skipped"]["file"] += 1
                    elif t == "input_audio":
                        skipped_audios += 1
                        stats["skipped"]["audio"] += 1
                if multimodal and skipped_images > 0:
                    content_parts = _build_content_parts(item["content"])

            if multimodal and content_parts:
                msg: dict = {"role": role, "content": content_parts}
                if item.get("reasoning_content"):
                    msg["reasoning_content"] = item["reasoning_content"]
                if item.get("tool_calls"):
                    msg["tool_calls"] = item["tool_calls"]
                if item.get("tool_call_id"):
                    msg["tool_call_id"] = item["tool_call_id"]
                messages.append(msg)
            elif text_content:
                hints = []
                if skipped_images > 0 and role == "user":
                    h = "image" if skipped_images == 1 else f"{skipped_images} images"
                    hints.append(h)
                    log.warn(f"{h} skipped, multimodal mode is off")
                if skipped_files > 0 and role == "user":
                    h = "file" if skipped_files == 1 else f"{skipped_files} files"
                    hints.append(h)
                    log.warn(f"{h} skipped, file input not supported")
                if skipped_audios > 0 and role == "user":
                    h = "audio clip" if skipped_audios == 1 else f"{skipped_audios} audio clips"
                    hints.append(h)
                    log.warn(f"{h} skipped, audio input not supported")
                if hints:
                    joined = " and ".join(hints)
                    text_content += (
                        f"\n\n[Note: The user attached {joined} which could not be "
                        "processed by the bridge. Do NOT describe or speculate about "
                        "the attachment content — just let the user know you cannot "
                        "view it and ask them to describe it in text if needed.]"
                    )
                msg: dict = {"role": role, "content": text_content}
                if item.get("reasoning_content"):
                    msg["reasoning_content"] = item["reasoning_content"]
                if item.get("tool_calls"):
                    msg["tool_calls"] = item["tool_calls"]
                if item.get("tool_call_id"):
                    msg["tool_call_id"] = item["tool_call_id"]
                messages.append(msg)
            elif skipped_images > 0 or skipped_files > 0 or skipped_audios > 0:
                parts = []
                if skipped_images > 0:
                    parts.append("image" if skipped_images == 1 else f"{skipped_images} images")
                if skipped_files > 0:
                    parts.append("file" if skipped_files == 1 else f"{skipped_files} files")
                if skipped_audios > 0:
                    parts.append("audio" if skipped_audios == 1 else f"{skipped_audios} audios")
                log.warn(f"attachment-only message skipped: {', '.join(parts)}")
            continue

        # --- type: message (inline content) ---
        if item.get("type") == "message":
            text_content = extract_text(item.get("content"))
            if text_content:
                messages.append({"role": "user", "content": text_content})
            continue

        stats["skipped"]["other"] += 1

    # Handle reasoning_content stripping / preservation
    if keep_reasoning_content:
        stats["preservedReasoningContent"] = sum(
            1 for m in messages if m.get("reasoning_content")
        )
    else:
        for m in messages:
            if "reasoning_content" in m:
                del m["reasoning_content"]
                stats["strippedReasoningContent"] += 1

    return {"messages": messages, "stats": stats}


def last_user_text(messages: list[dict]) -> str:
    """Return the text content of the last user message."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return extract_text(messages[i].get("content"))
    return ""


def translate_tools(raw_tools: Any) -> list[dict]:
    """Translate Responses API tools to Chat Completions tools."""
    if not isinstance(raw_tools, list):
        return []
    result = []
    for t in raw_tools:
        tool_type = t.get("type", "")
        # Built-in tools that have no Chat Completions equivalent
        if tool_type in ("web_search", "file_search", "code_interpreter",
                         "computer_use", "mcp", "image_gen", "shell"):
            log.warn(f"built-in tool not supported by Chat API: {tool_type}")
            continue
        name = t.get("name") or t.get("function", {}).get("name")
        if not name:
            if tool_type:
                log.warn(f"tool skipped (no name): type={tool_type}")
            continue
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": t.get("description")
                or t.get("function", {}).get("description", ""),
                "parameters": t.get("parameters")
                or t.get("function", {}).get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            },
        })
    return result


def translate_tool_choice(tool_choice: Any) -> Any:
    """Translate Responses API tool_choice to Chat Completions tool_choice."""
    if not tool_choice:
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    if (
        isinstance(tool_choice, dict)
        and tool_choice.get("type") == "function"
        and tool_choice.get("name")
    ):
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return tool_choice
