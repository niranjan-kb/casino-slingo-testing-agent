"""Smoke test for goal_casino_session — authenticate-only path.

Resets the casino app, starts a fresh agent-workflow, sends "login", and watches
the worker log for a `LOGIN PASS` marker. Exits 0 on success, 1 on timeout or
any explicit failure marker.

Usage:
    uv run scripts/smoke_login.py [--timeout 300]

Pre-requisites (asserted at startup):
    - api on http://127.0.0.1:8000
    - android-worker running, logging to /tmp/android-worker.log
    - emulator connected via adb (ANDROID_SERIAL)
    - .env has AGENT_GOAL=goal_casino_session (else this script forces it via env var)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8000"
WORKER_LOG = "/tmp/android-worker.log"
APP_PACKAGE = os.getenv("APP_PACKAGE", "com.betfanatics.casino.test")

PASS_RE = re.compile(r"LOGIN PASS")
FAIL_RE = re.compile(r"login_failed|otp_failed|login_unverified|LOGIN FAIL|Traceback")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=300, help="seconds to wait for LOGIN PASS")
    args = parser.parse_args()

    if not _check_api_up():
        print(f"[smoke] api not reachable at {API}", file=sys.stderr)
        return 1

    if not shutil.which("adb"):
        print("[smoke] adb not in PATH", file=sys.stderr)
        return 1

    if not os.path.exists(WORKER_LOG):
        print(f"[smoke] worker log not found at {WORKER_LOG} — is the worker running?", file=sys.stderr)
        return 1

    print(f"[smoke] resetting app: {APP_PACKAGE}")
    subprocess.run(["adb", "shell", "am", "force-stop", APP_PACKAGE], check=True)
    subprocess.run(["adb", "shell", "pm", "clear", APP_PACKAGE], check=True)

    log_offset = os.path.getsize(WORKER_LOG)

    print("[smoke] starting fresh workflow")
    _post("/start-workflow")
    time.sleep(1.0)

    print("[smoke] sending 'login' prompt")
    _post("/send-prompt", "?prompt=login")

    deadline = time.time() + args.timeout
    print(f"[smoke] watching {WORKER_LOG} for LOGIN PASS (timeout {args.timeout}s)")

    while time.time() < deadline:
        time.sleep(2)
        size = os.path.getsize(WORKER_LOG)
        if size <= log_offset:
            continue
        with open(WORKER_LOG, "rb") as f:
            f.seek(log_offset)
            new = f.read(size - log_offset).decode("utf-8", errors="replace")
        log_offset = size
        if PASS_RE.search(new):
            print("[smoke] PASS — agent reached home")
            return 0
        m = FAIL_RE.search(new)
        if m:
            print(f"[smoke] FAIL — saw {m.group(0)}", file=sys.stderr)
            return 1

    print(f"[smoke] FAIL — no LOGIN PASS within {args.timeout}s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
