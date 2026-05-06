---
name: run-agent
description: Start the full Slingo QA testing agent stack (Docker infra, appium-mcp SSE server, Android Temporal worker) and print a service status table with URLs. Optionally also kick off a workflow when the arg `--with-workflow` is passed. Use when the user says "run the agent", "start the agent", "bring up the stack", or similar.
allowed-tools: Bash, Read
---

# Run the Slingo QA Agent

Start the full Slingo QA testing agent pipeline (Docker infra + appium-mcp + Android worker), then print a service status table. By default, **do not** start a workflow — the user kicks that off from the frontend or `curl`. If the user passes `--with-workflow` (or asks to "also start a workflow"), include step 6.

## Prerequisites (must be done by the user before this skill runs)

- **Docker Desktop** running (`docker info` succeeds)
- **Android emulator** connected (`adb devices` shows at least one `device`)
- **AWS SSO** session valid for Bedrock (`aws sts get-caller-identity --profile bedrock`)
- **ANDROID_HOME** exported in the shell

If any of these fail, stop and ask the user to fix — do not attempt workarounds.

## Startup sequence

### 1. Parallel prerequisite checks

Run these in a single message in parallel:

- `docker info | head -3`
- `adb devices`
- `aws sts get-caller-identity --profile bedrock`
- `echo "ANDROID_HOME=$ANDROID_HOME"`
- `lsof -iTCP:3100 -sTCP:LISTEN 2>/dev/null` — is appium-mcp already up?
- `pgrep -f run_worker_android.py` — is worker already up?

If a port is already in use or a process is already running, reuse it — don't duplicate.

### 2. Start Docker infra

```bash
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend -d
```

If Temporal fails with "dependency failed to start" (postgres race), re-run the same command — postgres will be healthy on the second attempt. If any container is in a broken `exited` state, run `docker compose -f docker-compose.yml down` first, then `up`.

### 3. Start appium-mcp SSE server (background)

Skip if port 3100 is already listening.

```bash
ANDROID_HOME=$ANDROID_HOME npx -y appium-mcp@1.56.3 --httpStream --port=3100
# Pinned to 1.56.3 — 1.57+ consolidated/renamed tools (create_session, appium_click,
# appium_swipe, etc.) and breaks the Slingo goal's _ANDROID_TOOLS list. Do not
# bump without updating goals/slingo_qa_android/__init__.py + prompts/tools.md.
```

Run in background (`run_in_background: true`). Wait for port 3100 to listen:

```bash
until lsof -iTCP:3100 -sTCP:LISTEN >/dev/null 2>&1; do sleep 2; done
```

### 4. Start Android worker (background)

Skip if `run_worker_android.py` is already running.

```bash
PYTHONUNBUFFERED=1 PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run -- python -u scripts/run_worker_android.py
```

**Critical**: `PYTHONUNBUFFERED=1` + `python -u` — without both, Python buffers stdout and worker logs appear empty for 30+ seconds, making it impossible to verify startup.

Run in background, then poll the output file until one of these markers appears:

- Success: `Android worker ready to process tasks!`
- Failure: `Traceback`

```bash
until grep -q "Android worker ready\|Traceback" <output_file>; do sleep 2; done
```

### 5. Verify & print the service status table

Run port + HTTP checks:

```bash
for p in 5173 8080 8000 3100 7233; do
  lsof -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && echo "OK :$p" || echo "DOWN :$p"
done
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs
adb devices | tail -n +2 | head -1
```

Then output **exactly** this table (box-drawing chars, fixed column widths). Replace the status cells with what you observed — use `200 OK` for HTTP 200, `listening` for raw-socket services, the device serial for the emulator row:

```
┌────────────────────┬────────────────────────────┬───────────┐
│      Service       │            URL             │  Status   │
├────────────────────┼────────────────────────────┼───────────┤
│ Frontend           │ http://localhost:5173      │ 200 OK    │
├────────────────────┼────────────────────────────┼───────────┤
│ Temporal UI        │ http://localhost:8080      │ 200 OK    │
├────────────────────┼────────────────────────────┼───────────┤
│ API (FastAPI docs) │ http://localhost:8000/docs │ 200 OK    │
├────────────────────┼────────────────────────────┼───────────┤
│ appium-mcp (SSE)   │ http://localhost:3100/sse  │ listening │
├────────────────────┼────────────────────────────┼───────────┤
│ Temporal gRPC      │ localhost:7233             │ listening │
├────────────────────┼────────────────────────────┼───────────┤
│ Android emulator   │ emulator-5554              │ device    │
└────────────────────┴────────────────────────────┴───────────┘
```

If any row's status is not healthy, use `DOWN` (or the HTTP code) and flag it to the user instead of silently reporting success.

Follow the table with a one-liner showing how to kick off a workflow:

```bash
curl -s -X POST http://127.0.0.1:8000/start-workflow
```

### 6. (Optional) Start workflow

Only run this step when the user passed `--with-workflow` (or explicitly asked to also start a workflow).

```bash
curl -s -X POST http://127.0.0.1:8000/start-workflow
```

The API auto-terminates any stale `agent-workflow` before starting a new one. Print the response body so the user sees the goal's starter prompt.

## Common issues

- **AWS SSO expired** — `aws sso login --profile bedrock`. Must be fixed manually.
- **Docker daemon down** — `open -a Docker`, then wait until `docker info` succeeds.
- **Temporal "dependency failed to start"** — postgres wasn't ready. Re-run the compose `up` command.
- **Stale exited containers** — `docker compose -f docker-compose.yml down` then `up`.
- **appium-mcp port 3100 in use** — `pkill -f "appium-mcp --httpStream"` then restart.
- **Worker output empty for 30+s** — missing `PYTHONUNBUFFERED=1` / `python -u`.
- **Zombie worker** — `pkill -9 -f run_worker_android.py` then restart.
- **`uv` VIRTUAL_ENV warning** — harmless; uv uses the project `.venv` regardless.

## Port reference

| Port | Service           |
|------|-------------------|
| 5173 | Frontend (Vite)   |
| 8000 | FastAPI           |
| 8080 | Temporal UI       |
| 7233 | Temporal gRPC     |
| 3100 | appium-mcp SSE    |
