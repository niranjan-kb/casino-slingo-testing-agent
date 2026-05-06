# Contract: MCP Server Definitions

**Feature**: 002-multiplatform-slingo-qa

---

## get_appium_mcp_server_definition(platform, included_tools)

**File**: `shared/mcp_config.py`

**Signature**:
```python
def get_appium_mcp_server_definition(
    platform: str,                  # "android" | "ios"
    included_tools: list[str],
) -> MCPServerDefinition
```

**Returns**:
```python
MCPServerDefinition(
    name="appium-mcp",
    command="npx",
    args=["-y", "appium-mcp@latest"],
    env={
        "ANDROID_HOME": os.getenv("ANDROID_HOME", ""),
        "CAPABILITIES_CONFIG": os.getenv("CAPABILITIES_CONFIG", ""),
        "NO_UI": "true",   # Disable appium-mcp UI to reduce token usage
    },
    included_tools=included_tools,
)
```

**Constraints**:
- `included_tools` must not be empty (Rule GD-4)
- `platform` must be "android" or "ios"
- Caller is responsible for macOS check before using platform="ios"

---

## get_playwright_mcp_server_definition(included_tools)

**File**: `shared/mcp_config.py`

**Signature**:
```python
def get_playwright_mcp_server_definition(
    included_tools: list[str],
) -> MCPServerDefinition
```

**Returns**:
```python
MCPServerDefinition(
    name="playwright-mcp",
    command="npx",
    args=["-y", "@playwright/mcp@latest"],
    env={
        "BROWSERSTACK_PLAYWRIGHT_URL": os.getenv("BROWSERSTACK_PLAYWRIGHT_URL", ""),
    },
    included_tools=included_tools,
)
```

**Constraints**:
- `included_tools` must not be empty (Rule GD-4)
- When `BROWSERSTACK_PLAYWRIGHT_URL` is empty, connects to local browser
- When set, connects to BrowserStack remote browser — no code changes needed

---

## Worker Startup Protocol

**Files**: `scripts/run_worker_android.py`, `scripts/run_worker_ios.py`, `scripts/run_worker_web.py`

Each worker script follows this startup sequence:

```
1. Load .env (dotenv)
2. Read PLATFORM env var
3. [iOS only] Assert platform.system() == "Darwin" → sys.exit(1) if not
4. Derive task queue: casino-qa-{PLATFORM}
5. Derive default goal: goal_slingo_qa_{PLATFORM}
6. Set TEMPORAL_TASK_QUEUE if not already set
7. Set AGENT_GOAL if not already set
8. Start Temporal worker on derived task queue
```

**Environment variables consumed**:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PLATFORM` | Yes | — | `android`, `ios`, or `web` |
| `BUILD_ENV` | No | `dev` | App environment |
| `BUILD_TYPE` | No | `debug` | Build type |
| `PRODUCT_FLAVOR` | No | `casino` | App flavor |
| `TEMPORAL_ADDRESS` | No | `localhost:7233` | Temporal server |
| `TEMPORAL_TASK_QUEUE` | No | derived | Overrides derived queue |
| `AGENT_GOAL` | No | derived | Overrides derived goal |
| `ANDROID_HOME` | Android only | — | Android SDK path |
| `CAPABILITIES_CONFIG` | No | — | Path to Appium capabilities JSON |
| `BROWSERSTACK_USERNAME` | No | — | BrowserStack auth |
| `BROWSERSTACK_ACCESS_KEY` | No | — | BrowserStack auth |
| `BROWSERSTACK_APPIUM_URL` | No | — | BrowserStack Appium endpoint |
| `BROWSERSTACK_PLAYWRIGHT_URL` | No | — | BrowserStack Playwright endpoint |
| `TEST_EMAIL` | Yes | — | QA test account email |
| `TEST_PASSWORD` | Yes | — | QA test account password |
| `LLM_MODEL` | No | `openai/gpt-4o` | LLM for planning |
| `LLM_KEY` | Yes | — | LLM API key |

---

## BrowserStack Capabilities Config Schema

**File**: `capabilities/browserstack-android.json` (template)

```json
{
  "platformName": "Android",
  "appium:deviceName": "Samsung Galaxy S23",
  "appium:platformVersion": "13.0",
  "appium:app": "bs://<android_app_id>",
  "appium:automationName": "UiAutomator2",
  "appium:noReset": true,
  "bstack:options": {
    "userName": "${BROWSERSTACK_USERNAME}",
    "accessKey": "${BROWSERSTACK_ACCESS_KEY}",
    "projectName": "Fanatics Casino QA",
    "buildName": "casino-qa-android-${BUILD_ENV}"
  }
}
```

**Note**: `${VAR}` tokens are substituted at runtime by the worker startup script. The capabilities file itself is static; only the env vars change between local and BrowserStack runs.
