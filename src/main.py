"""codex-bridge entry point.

Starts two components:
1. Config watcher (background thread) — polls ~/.codex/config.toml for -cb- prefix
2. HTTP proxy server (main thread) — translates Responses API ↔ Chat Completions API

Zero configuration required — just run it.
"""

import argparse
import threading

from . import log
from .server import create_server
from .watcher import watch


def run():
    parser = argparse.ArgumentParser(
        description="codex-bridge — zero-config proxy for Codex CLI"
    )
    parser.add_argument("--port", type=int, default=10110, help="listen port (default: 10110)")
    parser.add_argument("--poll-interval", type=float, default=5, help="config poll interval in seconds (default: 5)")
    parser.add_argument("--timeout", type=int, default=30, help="upstream API timeout in minutes (default: 30)")
    parser.add_argument("--multimodal", action="store_true", help="enable multimodal (image) support")
    args = parser.parse_args()

    PORT = args.port
    TIMEOUT = args.timeout * 60
    POLL_INTERVAL = args.poll_interval
    MULTIMODAL = args.multimodal

    print("")
    log.header("codex-bridge")
    log.info(f"proxy:          http://127.0.0.1:{PORT}")
    log.info(f"multimodal:     {'on' if MULTIMODAL else 'off'}")
    log.info(f"poll interval:  {POLL_INTERVAL}s")
    log.info(f"upstream timeout: {args.timeout}min")
    print("")

    # Start config watcher in background thread
    stop_event = threading.Event()
    watcher_thread = threading.Thread(
        target=watch,
        args=(POLL_INTERVAL, PORT, stop_event),
        daemon=True,
        name="config-watcher",
    )
    watcher_thread.start()
    log.ok("config watcher started")

    # Start HTTP server in main thread
    server = create_server(
        port=PORT,
        timeout=TIMEOUT,
        multimodal=MULTIMODAL,
    )
    log.ok(f"server listening on http://127.0.0.1:{PORT}")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
        log.info("codex-bridge stopped")


if __name__ == "__main__":
    run()
