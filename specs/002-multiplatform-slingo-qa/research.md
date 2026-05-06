# Research: Multi-Platform Slingo QA Agent

**Feature**: 002-multiplatform-slingo-qa
**Date**: 2026-03-12

---

## Decision 1: appium-mcp Tool Names for included_tools

**Decision**: Use the following tool subset for Android/iOS mobile goals.

**Android included_tools**:
```
screenshot, appium_click, appium_double_tap, appium_set_value, appium_get_text,
appium_find_element, appium_activate_app, appium_terminate_app, appium_get_contexts,
appium_switch_context, appium_press_key, appium_handle_alert, scroll, swipe,
create_session, delete_session, select_platform, select_device
```

**iOS additional tools** (beyond Android set):
```
boot_simulator, setup_wda, appium_deep_link
```

**Rationale**: appium-mcp v1.26.0 exposes 40+ tools. The selected subset covers all Slingo QA interactions: screenshot, tap, type, scroll, app lifecycle, context switching (for WebView detection), and session management. `boot_simulator` and `setup_wda` are iOS-only; they are unnecessary on Android.

**Alternatives considered**: Including all tools — rejected because FR-018 prohibits open-ended tool exposure. Narrower set reduces token cost and accidental tool calls.

---

## Decision 2: @playwright/mcp Tool Names for Web

**Decision**: Use the following tool subset for web goals.

**Web included_tools**:
```
browser_navigate, browser_click, browser_fill, browser_screenshot, browser_evaluate,
browser_wait_for, browser_select_option, browser_press_key, browser_close,
browser_snapshot, browser_network_requests
```

**Rationale**: `@playwright/mcp` (Microsoft) exposes browser automation tools prefixed with `browser_`. The selected subset covers navigation, interaction, form filling, screenshot capture, and network inspection — sufficient for login, game search, gameplay, and balance verification on the web app.

**Alternatives considered**: Using raw Playwright Python in activities — rejected by Rule MCP-2. Using Selenium — rejected by Rule MCP-2.

---

## Decision 3: BrowserStack Connection Mechanism

**Decision**: Use `CAPABILITIES_CONFIG` env var pointing to a JSON file containing Appium desired capabilities including `remote_url` for BrowserStack.

**appium-mcp supports `remoteServerUrl`** in the capabilities config:
```json
{
  "platformName": "Android",
  "appium:deviceName": "Samsung Galaxy S23",
  "appium:app": "bs://app_id",
  "remote_url": "https://<user>:<key>@hub.browserstack.com/wd/hub"
}
```

The `MCPServerDefinition.env` field passes `CAPABILITIES_CONFIG` to the npx process. The capabilities file path is set per environment. Local = local emulator config. BrowserStack = remote config. No goal code changes needed.

**Rationale**: appium-mcp v1.8.0+ supports `remoteServerUrl` with basic auth. BrowserStack's Appium endpoint uses standard basic auth (username + access key). This satisfies FR-010 and Rule SC-2.

**Playwright/web BrowserStack**: `@playwright/mcp` connects to BrowserStack via a remote CDP URL. The `BROWSERSTACK_PLAYWRIGHT_URL` env var is passed to the MCP server. Same pattern — local = no env, BrowserStack = set env var.

**Alternatives considered**: BrowserStack-specific SDK — rejected by Rule SC-3. Modifying goal code — rejected by FR-010.

---

## Decision 4: iOS macOS Platform Check

**Decision**: Each iOS worker script (`scripts/run_worker_ios.py`) performs a startup OS check using `platform.system()`.

```python
import platform, sys
if platform.system() != "Darwin":
    print(f"ERROR: iOS worker requires macOS. Current OS: {platform.system()}")
    print("iOS Simulator and XCUITest are macOS-only. Use a Mac or AWS EC2 Mac instance.")
    sys.exit(1)
```

**Rationale**: `platform.system()` returns `"Darwin"` on macOS, `"Linux"` on Linux, `"Windows"` on Windows. Fail-fast at startup satisfies FR-011 and PT-1. No framework changes needed — this is in the new worker script only.

**Alternatives considered**: Docker ENV check — insufficient, container could run on macOS. Runtime failure — rejected, fail-fast is required within 10 seconds (FR-011).

---

## Decision 5: PLATFORM Env Var → Task Queue + Goal Mapping

**Decision**: New platform-specific worker scripts read `PLATFORM` and derive both the task queue and default goal at startup, before importing `shared/config.py`.

```python
# scripts/run_worker_android.py
import os
platform_name = os.getenv("PLATFORM", "android").lower()
os.environ.setdefault("TEMPORAL_TASK_QUEUE", f"casino-qa-{platform_name}")
os.environ.setdefault("AGENT_GOAL", f"goal_slingo_qa_{platform_name}")
# Then imports proceed normally
```

This means `shared/config.py` is never modified (Rule FI-1) — it reads `TEMPORAL_TASK_QUEUE` from env as always. The worker script sets it before the import chain resolves it.

**Rationale**: Satisfies FR-019 (PLATFORM drives queue selection) and FI-1 (config.py frozen). One env var (`PLATFORM=android`) is sufficient; the rest are derived automatically.

**Alternatives considered**: Modifying `shared/config.py` — rejected by Rule FI-1. Separate config files per platform — unnecessary complexity.

---

## Decision 6: iOS Screen Map Resolution

**Decision**: iPhone 14 Pro Simulator (default in Xcode 15+) logical resolution is **393×852 pt**. Physical pixel resolution is **1179×2556 px** at 3x scale.

For screen map purposes, we key on the **logical resolution `393x852`** since iOS interaction coordinates are in logical points (Appium uses logical coordinates via XCUITest).

**Rationale**: Appium XCUITest driver reports and accepts coordinates in logical points, not physical pixels. Using logical resolution ensures screen map coordinates match tool call arguments. Contrast with Android where physical pixels are used.

**Note**: This must be verified against the actual Fanatics Casino iOS Simulator configuration used by the team. The default iPhone 14 Pro assumption should be confirmed.

**Alternatives considered**: Physical pixel resolution — causes coordinate mismatch with XCUITest driver.

---

## Decision 7: Screen Map Schema Update (Platform Partitioning)

**Decision**: Extend existing screen map files to include a `platform` field and move to platform-partitioned directories as specified in constitution v2.0.0.

Existing `screen_maps/platform/1080x1920.json` represents Android. New files:
- `screen_maps/platform/android/1080x1920.json` (copy + update from existing)
- `screen_maps/platform/ios/393x852.json` (new, coordinates TBD from Simulator)
- `screen_maps/games/slingo_cash_eruption/ios/393x852.json` (new)

**Rationale**: Constitution v2.0.0 mandates platform as primary partition in screen maps. Existing Android file content is preserved; only the directory structure changes.

---

## Decision 8: Docker Compose Update for Web Worker

**Decision**: Add a `web-worker` service to `docker-compose.yml` that runs `scripts/run_worker_web.py` with `PLATFORM=web`.

```yaml
web-worker:
  build:
    context: .
    dockerfile: Dockerfile
  environment:
    - PLATFORM=web
    - TEMPORAL_ADDRESS=temporal:7233
  env_file:
    - .env
  command: uv run scripts/run_worker_web.py
  depends_on:
    temporal:
      condition: service_healthy
  networks:
    - temporal-network
```

**Rationale**: Web worker is Docker-compatible (FR-012, Rule PT-4). Android and iOS workers are NOT added to docker-compose (Rules PT-1, PT-2) — they run as native processes.

---

## Unknowns Remaining (Verify Before Implementation)

1. **iOS bundle ID**: Confirm `com.betfanatics.casino` is the correct iOS bundle ID for the debug flavor (not the Android package name).
2. **iOS Simulator UDID**: `xcrun simctl list devices` output needed to get the actual test device UDID.
3. **iOS screen resolution**: Confirm the Simulator model and resolution used by the QA team — assumption is iPhone 14 Pro (393x852 logical).
4. **Fanatics Casino web URL**: The web app URL for each `BUILD_ENV` (dev/test/cert/prod) needs to be documented.
5. **BrowserStack app ID**: iOS `.ipa` and Android `.apk` must be uploaded to BrowserStack and their `bs://app_id` values documented.
6. **appium-mcp BrowserStack validation**: Confirm basic auth with BrowserStack Appium endpoint works with appium-mcp v1.26.0 before committing to it for prod.
