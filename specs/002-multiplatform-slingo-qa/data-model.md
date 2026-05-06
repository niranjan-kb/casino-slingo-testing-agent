# Data Model: Multi-Platform Slingo QA Agent

**Feature**: 002-multiplatform-slingo-qa
**Date**: 2026-03-12

---

## Existing Models (unchanged, reference only)

### MCPServerDefinition (models/tool_definitions.py — FROZEN)
```
name: str
command: str
args: List[str]
env: Optional[Dict[str, str]]
connection_type: str = "stdio"
included_tools: Optional[List[str]]
```

### AgentGoal (models/tool_definitions.py — FROZEN)
```
id: str
category_tag: str
agent_name: str
agent_friendly_description: str
tools: List[ToolDefinition]
description: str
starter_prompt: str
example_conversation_history: str
mcp_server_definition: Optional[MCPServerDefinition]
```

---

## New Entities

### AppiumMCPServerDefinition (logical, returned by shared/mcp_config.py)

A specialisation of `MCPServerDefinition` for appium-mcp. Not a new class — returned as a plain `MCPServerDefinition` instance by `get_appium_mcp_server_definition()`.

```
name:    "appium-mcp"
command: "npx"
args:    ["-y", "appium-mcp@latest"]
env:     {
           ANDROID_HOME: from os.getenv("ANDROID_HOME"),
           CAPABILITIES_CONFIG: from os.getenv("CAPABILITIES_CONFIG", "")
         }
included_tools: [platform-specific subset — see research.md Decision 1]
```

**Validation**: `included_tools` must not be empty (Rule GD-4).
**BrowserStack switching**: Set `CAPABILITIES_CONFIG` to point to a BrowserStack capabilities JSON file. No code change.

---

### PlaywrightMCPServerDefinition (logical, returned by shared/mcp_config.py)

A specialisation of `MCPServerDefinition` for @playwright/mcp. Returned as a plain `MCPServerDefinition` instance by `get_playwright_mcp_server_definition()`.

```
name:    "playwright-mcp"
command: "npx"
args:    ["-y", "@playwright/mcp@latest"]
env:     {
           BROWSERSTACK_PLAYWRIGHT_URL: from os.getenv("BROWSERSTACK_PLAYWRIGHT_URL", "")
         }
included_tools: [web tool subset — see research.md Decision 2]
```

**Validation**: `included_tools` must not be empty (Rule GD-4).
**BrowserStack switching**: Set `BROWSERSTACK_PLAYWRIGHT_URL`. No code change.

---

### PlatformWorkerConfig (logical, derived at worker startup)

Not a persistent model — resolved at startup from environment variables.

```
platform:   os.getenv("PLATFORM")          # "android" | "ios" | "web"
task_queue: f"casino-qa-{platform}"        # derived per Rule SC-1 / FR-017
agent_goal: f"goal_slingo_qa_{platform}"   # derived per FR-019
build_env:  os.getenv("BUILD_ENV", "dev")
build_type: os.getenv("BUILD_TYPE", "debug")
product_flavor: os.getenv("PRODUCT_FLAVOR", "casino")
```

**Validation**:
- `platform` must be one of `android`, `ios`, `web`
- `ios` platform requires `platform.system() == "Darwin"` (Rule PT-1, FR-011)

---

### BrowserStackCapabilitiesConfig (JSON file, referenced by CAPABILITIES_CONFIG)

Stored as a JSON file on disk, path set via `CAPABILITIES_CONFIG` env var.

**Android example (`capabilities/browserstack-android.json`)**:
```json
{
  "platformName": "Android",
  "appium:deviceName": "Samsung Galaxy S23",
  "appium:platformVersion": "13.0",
  "appium:app": "bs://<android_app_id>",
  "appium:automationName": "UiAutomator2",
  "bstack:options": {
    "userName": "<BROWSERSTACK_USERNAME>",
    "accessKey": "<BROWSERSTACK_ACCESS_KEY>",
    "projectName": "Fanatics Casino QA",
    "buildName": "casino-qa-android"
  }
}
```

**iOS example (`capabilities/browserstack-ios.json`)**:
```json
{
  "platformName": "iOS",
  "appium:deviceName": "iPhone 14 Pro",
  "appium:platformVersion": "16",
  "appium:app": "bs://<ios_app_id>",
  "appium:automationName": "XCUITest",
  "bstack:options": {
    "userName": "<BROWSERSTACK_USERNAME>",
    "accessKey": "<BROWSERSTACK_ACCESS_KEY>",
    "projectName": "Fanatics Casino QA",
    "buildName": "casino-qa-ios"
  }
}
```

---

### Screen Map — iOS Platform (new partition)

File: `screen_maps/platform/ios/393x852.json`
Mirrors Android structure, coordinates in **logical points** (not physical pixels).

```json
{
  "app": "fanatics_casino",
  "platform": "ios",
  "resolution": "393x852",
  "note": "Logical point coordinates for XCUITest/Appium. Device: iPhone 14 Pro Simulator.",
  "screens": {
    "home": {
      "visual_anchors": ["Bottom tab bar", "Featured games carousel", "Search icon"],
      "elements": {
        "search_bar": { "x": 197, "y": 120, "intent": "Tap to open game search", "type": "input" }
      },
      "last_verified": "TBD — must be verified against iOS Simulator",
      "device_verified": "iPhone_14_Pro_Simulator"
    },
    "game_header": {
      "visual_anchors": ["Native iOS navigation bar above WebView game"],
      "elements": {
        "close_button": { "x": 30, "y": 60, "intent": "Close game", "type": "button" },
        "account_button": { "x": 363, "y": 60, "intent": "Open account overlay", "type": "button" }
      },
      "last_verified": "TBD",
      "device_verified": "iPhone_14_Pro_Simulator"
    },
    "keep_playing_modal": {
      "visual_anchors": ["Modal overlay asking to keep playing"],
      "elements": {
        "no_thanks_exit": { "x": 197, "y": 620, "intent": "Exit game", "type": "button" }
      },
      "last_verified": "TBD",
      "device_verified": "iPhone_14_Pro_Simulator"
    },
    "fancash_prompt": {
      "visual_anchors": ["FanCash promotional overlay"],
      "elements": {
        "start_playing": { "x": 197, "y": 720, "intent": "Dismiss FanCash prompt", "type": "button" }
      },
      "last_verified": "TBD",
      "device_verified": "iPhone_14_Pro_Simulator"
    }
  }
}
```

**Note**: All iOS coordinates marked `TBD` must be verified by running the app on the Simulator before implementing Phase 5 (User Story 2). Android screen maps from spec-001 are reused unchanged.

---

### Screen Map — iOS Game (new partition)

File: `screen_maps/games/slingo_cash_eruption/ios/393x852.json`

Same game elements as Android but scaled to iOS logical points. The grid structure (5x5) and reel (1x5) have the same layout; coordinates differ due to resolution.

**Column x-values (iOS logical, 393x852)**: ~88, ~152, ~197, ~242, ~305
**Row y-values**: ~360, ~430, ~500, ~565, ~635
**Spin button**: ~197, ~760

**Note**: All values are estimates scaled from Android (1080x1920 physical → 393x852 logical). Must be verified against actual Simulator screenshots before implementation.

---

## New Files Added

```
shared/
  mcp_config.py                    # EDIT: add get_appium_mcp_server_definition(),
                                   #        get_playwright_mcp_server_definition()

goals/
  slingo_qa_android.py             # NEW: goal_slingo_qa_android
  slingo_qa_ios.py                 # NEW: goal_slingo_qa_ios
  slingo_qa_web.py                 # NEW: goal_slingo_qa_web
  __init__.py                      # EDIT: register 3 new goals

scripts/
  run_worker_android.py            # NEW: Android worker entry (platform check + queue derivation)
  run_worker_ios.py                # NEW: iOS worker entry (macOS check + queue derivation)
  run_worker_web.py                # NEW: Web worker entry (queue derivation)

screen_maps/
  platform/
    android/1080x1920.json         # NEW: copy of existing platform/1080x1920.json + platform field
    ios/393x852.json               # NEW: iOS logical coords (TBD)
  games/slingo_cash_eruption/
    android/1080x1920.json         # NEW: copy of existing game screen map + platform field
    ios/393x852.json               # NEW: iOS logical coords (TBD)

capabilities/
  local-android.json               # NEW: local emulator capabilities template
  local-ios.json                   # NEW: local simulator capabilities template
  browserstack-android.json        # NEW: BrowserStack Android capabilities template
  browserstack-ios.json            # NEW: BrowserStack iOS capabilities template

docker-compose.yml                 # EDIT: add web-worker service
.env.example                       # EDIT: add new env vars (FR-015)
```

## Files Never Modified

```
workflows/agent_goal_workflow.py
activities/tool_activities.py
shared/mcp_client_manager.py
shared/config.py
prompts/agent_prompt_generators.py
api/main.py
goals/slingo_qa.py                 # spec-001 frozen
```
