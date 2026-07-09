"""Reasoning content recovery for multi-turn tool-call conversations.

DeepSeek omits reasoning_content on tool-call assistant messages in multi-turn
conversations. This module remembers reasoning from the previous turn and
restores it on the next, so the reasoning chain stays intact across function
calls.

Uses threading.local() to isolate reasoning queues per thread (each Codex
request is served in its own thread by ThreadingHTTPServer).
"""

import threading

_local = threading.local()


def _get_queue() -> list[str]:
    """Get the per-thread reasoning queue, creating it if needed."""
    if not hasattr(_local, "queue"):
        _local.queue = []
    return _local.queue


def remember_reasoning(key: str, messages: list[dict]) -> None:
    """Store reasoning_content from assistant messages for later recovery."""
    q = _get_queue()
    for msg in messages:
        if (
            isinstance(msg, dict)
            and msg.get("role") == "assistant"
            and msg.get("reasoning_content")
        ):
            q.append(msg["reasoning_content"])


def recover_reasoning(key: str, messages: list[dict]) -> int:
    """Restore reasoning_content on tool-call messages that are missing it."""
    q = _get_queue()
    if not q:
        return 0
    recovered = 0
    for msg in messages:
        if (
            isinstance(msg, dict)
            and msg.get("role") == "assistant"
            and msg.get("tool_calls")
            and "reasoning_content" not in msg
        ):
            msg["reasoning_content"] = q[min(recovered, len(q) - 1)]
            recovered += 1
    return recovered


def session_key(body: dict) -> str:
    """Derive a session key from the request body.

    Uses previous_response_id when available for session correlation;
    falls back to thread identity for isolation.
    """
    prev = body.get("previous_response_id")
    if prev:
        return str(prev)
    return str(threading.get_ident())
