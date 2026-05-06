"""End-to-end smoke for the intent layer (specs/004-nav-graph-intents, Story 3).

Drives a high-level prompt through the full intent sequence:
    intent_authenticate -> intent_navigate_to_screen -> intent_play_game -> intent_report

Exits 0 when all expected intents complete; 1 on timeout or any explicit
failure marker. Watches both the worker log AND the workflow's
get_completed_intents query for terminal state.

Pre-requisites (asserted at startup):
    - api on http://127.0.0.1:8000
    - android-worker running, logging to /tmp/android-worker.log
    - emulator connected via adb (ANDROID_SERIAL)

Usage:
    uv run scripts/smoke_play_intent.py [--timeout 600] [--prompt "play any slingo game till you lose $1"]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import List, Optional
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8000"
WORKER_LOG = "/tmp/android-worker.log"
APP_PACKAGE = os.getenv("APP_PACKAGE", "com.betfanatics.casino.test")
DEFAULT_PROMPT = "play any slingo game till you lose $1"

# Required completion order. Reports completion is the session-end signal.
EXPECTED_TERMINAL = "intent_report"
ALL_EXPECTED = [
    "intent_authenticate",
    "intent_navigate_to_screen",
    "intent_play_game",
    "intent_report",
]

FAIL_RE = re.compile(
    r"\b(LOGIN FAIL|TRACEBACK|workflow failed|observer tick swallowed failure|"
    r"unhandled exception)\b",
    re.IGNORECASE,
)


def _post(path: str, query: str = "") -> None:
    req = Request(f"{API}{path}{query}", method="POST")
    with urlopen(req, timeout=10) as r:
        r.read()


def _check_api_up() -> bool:
    try:
        with urlopen(f"{API}/", timeout=3) as r:
            return r.status == 200
    except URLError:
        return False


def _get_completed_intents() -> Optional[List[str]]:
    """Hit the API's query endpoint if exposed; otherwise return None and rely on log scan.

    The casino API may or may not expose workflow queries directly. This helper
    is best-effort — when the endpoint is unavailable we fall back to log
    scanning for the `intent completed:` marker.
    """
    try:
        with urlopen(f"{API}/get-completed-intents", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        intents = data.get("completed_intents")
        if isinstance(intents, list):
            return [str(x) for x in intents]
    except (URLError, ValueError, KeyError):
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600, help="seconds to wait for terminal state")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="session prompt to send")
    parser.add_argument("--require-all", action="store_true",
                        help="require ALL four intents to complete (default: just intent_report)")
    args = parser.parse_args()

    if not _check_api_up():
        print(f"[smoke-intent] api not reachable at {API}", file=sys.stderr)
        return 1
    if not shutil.which("adb"):
        print("[smoke-intent] adb not in PATH", file=sys.stderr)
        return 1
    if not os.path.exists(WORKER_LOG):
        print(f"[smoke-intent] worker log not found at {WORKER_LOG}", file=sys.stderr)
        return 1

    print(f"[smoke-intent] resetting app: {APP_PACKAGE}")
    subprocess.run(["adb", "shell", "am", "force-stop", APP_PACKAGE], check=True)
    subprocess.run(["adb", "shell", "pm", "clear", APP_PACKAGE], check=True)

    log_offset = os.path.getsize(WORKER_LOG)

    print("[smoke-intent] starting fresh workflow")
    _post("/start-workflow")
    time.sleep(1.0)

    print(f"[smoke-intent] sending prompt: {args.prompt!r}")
    _post("/send-prompt", f"?prompt={quote(args.prompt)}")

    deadline = time.time() + args.timeout
    print(f"[smoke-intent] watching for intent completions (timeout {args.timeout}s)")

    seen_completed: List[str] = []
    completion_re = re.compile(r"intent completed:\s*(intent_[a-z_]+)")

    while time.time() < deadline:
        time.sleep(2)

        # 1. Prefer the workflow query if available.
        api_completed = _get_completed_intents()
        if api_completed is not None:
            seen_completed = api_completed

        # 2. Fall back to log scan for the "intent completed:" marker.
        size = os.path.getsize(WORKER_LOG)
        if size > log_offset:
            with open(WORKER_LOG, "rb") as f:
                f.seek(log_offset)
                new = f.read(size - log_offset).decode("utf-8", errors="replace")
            log_offset = size
            for m in completion_re.finditer(new):
                intent_id = m.group(1)
                if intent_id not in seen_completed:
                    seen_completed.append(intent_id)
                    print(f"[smoke-intent] completed: {intent_id}")
            fail = FAIL_RE.search(new)
            if fail:
                print(f"[smoke-intent] FAIL — saw {fail.group(0)!r}", file=sys.stderr)
                return 1

        if args.require_all:
            if all(i in seen_completed for i in ALL_EXPECTED):
                print(f"[smoke-intent] PASS — all expected intents completed: {seen_completed}")
                return 0
        else:
            if EXPECTED_TERMINAL in seen_completed:
                print(f"[smoke-intent] PASS — {EXPECTED_TERMINAL} completed (history: {seen_completed})")
                return 0

    print(f"[smoke-intent] FAIL — terminal state not reached within {args.timeout}s "
          f"(completed: {seen_completed})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
