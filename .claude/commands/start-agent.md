# Start the Slingo QA Agent

Start the full Slingo QA testing agent pipeline (infrastructure + appium-mcp + worker + workflow).

## Prerequisites
- Docker running
- Android emulator running (`emulator-5554`)
- AWS SSO session valid (`aws sso login --profile bedrock` if expired)

## Steps

1. **Check Docker infrastructure** — start Temporal, PostgreSQL, API, Frontend, Temporal UI if not running
2. **Check appium-mcp SSE server** — start persistent server on port 3100 if not running (`ANDROID_HOME=$ANDROID_HOME npx appium-mcp --httpStream --port=3100`)
3. **Check Android worker** — start worker if not running (`PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py`)
4. **Terminate any stale workflow** — use Temporal client to terminate existing `agent-workflow` if it's in RUNNING state
5. **Start fresh workflow** — `curl -s -X POST http://127.0.0.1:8000/start-workflow`
6. **Verify** — check worker logs confirm: MCP tools loaded (18 tools), persistent SSE connection established

## Key ports
- Temporal: 7233
- Temporal UI: 8080
- API: 8000
- Frontend: 5173
- appium-mcp SSE: 3100

## Common issues
- **AWS SSO expired**: `aws sso login --profile bedrock`
- **ANDROID_HOME missing**: Ensure it's exported in the shell starting appium-mcp and worker
- **Stale workflow**: `curl -s -X POST http://127.0.0.1:8000/start-workflow` auto-terminates stale ones
- **appium-mcp port in use**: `pkill -f "appium-mcp --httpStream"` then restart

Run all checks and start any missing components. Report status of each.
