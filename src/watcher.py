"""Config watcher: periodically polls ~/.codex/config.toml for -cb- prefix.

When a model name starts with "-cb-", the watcher:
1. Backs up the original config to ~/.codex/config.toml.cb.bak
2. Rewrites config.toml: base_url → http://localhost:10110, strips -cb- from model

When no -cb- prefix is found, the watcher does nothing.
"""

import os
import re
import shutil
import threading
import time
import tomllib

from . import log

CONFIG_PATH = os.path.expanduser("~/.codex/config.toml")
BACKUP_PATH = os.path.expanduser("~/.codex/config.toml.cb.bak")
CB_PREFIX = "-cb-"


def _find_model_line(lines: list[str]) -> int:
    """Find the line index of 'model = ...' in the TOML file."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^model\s*=\s*"', stripped):
            return i
    return -1


def _read_config() -> dict | None:
    """Read and parse ~/.codex/config.toml. Returns None if unreadable."""
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def _extract_model(config: dict) -> str:
    """Extract the model name from a parsed config dict."""
    return str(config.get("model", ""))


def _has_cb_prefix(model: str) -> bool:
    """Check if the model name starts with the -cb- prefix."""
    return model.startswith(CB_PREFIX)


def _strip_cb_prefix(model: str) -> str:
    """Remove the -cb- prefix from the model name."""
    return model[len(CB_PREFIX):]


def _backup_config() -> bool:
    """Backup config.toml to config.toml.cb.bak."""
    try:
        shutil.copy2(CONFIG_PATH, BACKUP_PATH)
        log.ok(f"backup: {BACKUP_PATH}")
        return True
    except Exception as e:
        log.err(f"backup failed: {e}")
        return False



def _get_upstream_host(config: dict) -> str:
    """Extract the upstream base_url (netloc + path) from the active provider."""
    provider_key = config.get("model_provider", "custom")
    provider = config.get("model_providers", {}).get(provider_key, {})
    base_url = provider.get("base_url", "")
    if not base_url:
        return ""
    # Remove scheme, keep netloc + path
    # https://api.deepseek.com → api.deepseek.com
    # https://coding.dashscope.aliyuncs.com/v1 → coding.dashscope.aliyuncs.com/v1
    return re.sub(r'^https?://', '', base_url).rstrip('/')


def _rewrite_config(original_model: str, upstream_host: str, bridge_port: int) -> bool:
    """Rewrite config.toml with bridge settings.

    Changes:
    - base_url → http://localhost:{bridge_port}/{upstream_host}
    - model → original_model with -cb- prefix stripped
    """
    try:
        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()

        new_model = _strip_cb_prefix(original_model)
        bridge_url = f"http://localhost:{bridge_port}/{upstream_host}"

        modified = False
        model_idx = _find_model_line(lines)

        # Rewrite model line
        if model_idx >= 0:
            lines[model_idx] = re.sub(
                r'(model\s*=\s*)".*"',
                f'\\1"{new_model}"',
                lines[model_idx],
            )
            modified = True
        else:
            lines.append(f'\nmodel = "{new_model}"\n')
            modified = True

        # Rewrite base_url in ALL provider sections
        new_lines = []
        in_provider = False
        for line in lines:
            if re.match(r'^\s*\[model_providers\.', line):
                in_provider = True
                new_lines.append(line)
            elif in_provider and re.match(r'^\s*base_url\s*=', line):
                new_lines.append(f'base_url = "{bridge_url}"\n')
                modified = True
            elif re.match(r'^\s*\[', line) and in_provider:
                in_provider = False
                new_lines.append(line)
            else:
                new_lines.append(line)
        lines = new_lines

        if modified:
            with open(CONFIG_PATH, "w") as f:
                f.writelines(lines)
            log.ok(
                f"rewrote config: model={new_model} base_url={bridge_url}"
            )
        return modified
    except Exception as e:
        log.err(f"rewrite failed: {e}")
        return False


def watch(poll_interval: float, port: int, stop_event: threading.Event) -> None:
    """Main watch loop. Runs in a background thread.

    Periodically reads ~/.codex/config.toml. When the model name starts
    with "-cb-", backs up the config and rewrites it to route through
    this bridge. Otherwise, does nothing.
    """
    while not stop_event.is_set():
        try:
            config = _read_config()
            if config is None:
                time.sleep(poll_interval)
                continue

            model = _extract_model(config)

            if _has_cb_prefix(model):
                upstream = _get_upstream_host(config)
                if not upstream:
                    log.err("cannot determine upstream base_url from config")
                    time.sleep(poll_interval)
                    continue
                log.info(f"detected -cb- prefix model: {model}")
                _backup_config()
                _rewrite_config(model, upstream, port)
        except Exception as e:
            log.err(f"watcher error: {e}")

        time.sleep(poll_interval)
