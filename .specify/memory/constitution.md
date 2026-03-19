# Fanatics Casino QA Agent Constitution

## Identity

This project is an AI-powered QA testing agent for the **Fanatics Casino** mobile and web applications, built by **Fanatics Betting & Gaming (FBG)**. FBG is a casino operator, not a game studio. We test our app as a platform — game engines are owned by providers (Gaming Realms, Evolution, IGT, Light & Wonder, etc.). Our concern is: does our app correctly wrap, launch, settle, and account for every game across every device, environment, and jurisdiction?

---

## Core Principles

### I. Same Architecture, New Goal — The LLM Is the Brain

We do NOT build new workflows or modify `AgentGoalWorkflow`. The existing agent loop is unchanged. We add new **goals** that use platform-specific MCP tools. The LLM decides every action:

1. LLM receives: goal description + tools list + conversation history (including screenshot results)
2. LLM responds: `{ "next": "confirm", "tool": "<tool_name>", "args": {...} }`
3. User confirms (or auto-confirms if `SHOW_CONFIRM=False`)
4. Tool executes as Temporal activity via `mcp_tool_activity`
5. Result goes back into conversation history
6. LLM sees result, decides next tool — LOOP
7. When done: `"next": "done"`, returns test report

The goal description encodes all domain knowledge (game rules, screen map coordinates, QA instructions). The LLM uses this to make decisions.

### II. Every Device/External Interaction Is an MCP Call

All interaction with devices, browsers, network proxies, and feature flag systems goes through MCP servers. No direct ADB commands, no subprocess calls to device tools, no direct Selenium or Playwright calls in workflow code. MCP is the only interface to the outside world. Temporal activities wrap MCP tool calls for durability and retry.

**Designated MCP servers by platform:**

| Platform | MCP Server | Launch Command | Notes |
|----------|-----------|----------------|-------|
| Android | `appium-mcp` | `npx appium-mcp@latest` | Replaces mobile-mcp post spec-001 |
| iOS | `appium-mcp` | `npx appium-mcp@latest` | macOS required |
| Web | `@playwright/mcp` | `npx @playwright/mcp@latest` | Docker-compatible |
| Android (demo/legacy) | `mobile-mcp` | `npx @mobilenext/mobile-mcp@latest` | spec-001 only, do not use in new goals |
| Network proxy (Phase 2) | `proxyman-mcp` | TBD | HTTP inspection |
| Feature flags (Phase 2) | `launchdarkly-mcp` | TBD | Flag toggling |

### III. Screen Map Is Domain Knowledge in the Prompt

The screen map is a structured JSON knowledge base partitioned by **platform** and **resolution**. It is loaded into the goal description so the LLM has coordinate knowledge when deciding where to tap.

Screen maps are append-only in production. Existing entries are never deleted without review. New resolutions and platforms are added as new partitions.

### IV. One Goal Per Platform Per Test Scenario

Each test scenario on each platform is a separate **goal** — not a separate workflow. `AgentGoalWorkflow` is the only workflow. A goal for Android and a goal for iOS covering the same game are two different goals.

Goals can chain via the existing `ChangeGoal` tool. For full test suites, a parent orchestrator (or multi-goal mode) chains goals in sequence.

### V. Adding a New Game = Adding New Goal Files (One Per Platform)

Adding a new game means:
1. Write goal files per platform (e.g., `goals/blackjack_qa_android.py`, `goals/blackjack_qa_ios.py`, `goals/blackjack_qa_web.py`)
2. Add screen map entries per platform and resolution
3. Register all goals in `goals/__init__.py`

No new workflows, activities, or MCP tools needed.

### VI. Human Approval at Financial Boundaries

The agent requires human confirmation before:
- Placing a bet (confirms amount)
- Purchasing extra spins (costs money)
- Making deposits or withdrawals
- Applying promotional codes
- Any action that spends real or bonus funds

Autonomous actions (navigation, screenshots, screen reading, tapping non-financial UI) proceed without confirmation.

---

## Hard Rules

These rules are non-negotiable. Any spec or implementation that violates them must be rejected or amended before proceeding.

### Platform Topology Rules

**RULE PT-1**: iOS workers MUST run on macOS. No exceptions. Docker, Linux, and Windows are categorically incompatible with iOS Simulator and XCUITest. An iOS worker started on a non-macOS host MUST fail at startup with an explicit error message within 10 seconds.

**RULE PT-2**: Android workers on macOS MUST run outside Docker. Docker Desktop on Mac does not expose KVM. The Android emulator requires hardware virtualization. Android workers on macOS run as native processes.

**RULE PT-3**: Android workers on Linux hosts MAY run inside Docker if and only if the host exposes `/dev/kvm` to the container. This is the required configuration for Linux EC2 instances.

**RULE PT-4**: Web workers MUST be Docker-compatible. A web worker that cannot run inside a standard Docker container is non-compliant. This is a portability requirement.

**RULE PT-5**: Each worker process is single-platform. A single worker process MUST NOT serve multiple platforms. No multi-platform workers.

### MCP Layer Rules

**RULE MCP-1**: `mobile-mcp` (`@mobilenext/mobile-mcp`) is legacy. It is used exclusively in `goal_slingo_qa` (spec-001) for the demo. All new mobile goals MUST use `appium-mcp`. New goals MUST NOT reference mobile-mcp.

**RULE MCP-2**: `@playwright/mcp` is the exclusive web tool layer. No direct Selenium, WebDriver, or raw Playwright subprocess calls in goal or workflow code.

**RULE MCP-3**: Each worker process spawns exactly one MCP server process. One worker = one device = one MCP process = one active session. Concurrency is achieved by running multiple workers, not multiple sessions within one worker.

**RULE MCP-4**: MCP server definitions are the ONLY sanctioned way to add new device or tool capabilities. No direct subprocess calls in activities or workflows.

### Scalability Rules

**RULE SC-1**: Each platform has its own dedicated Temporal task queue. Queue naming convention: `casino-qa-{platform}` (e.g., `casino-qa-android`, `casino-qa-ios`, `casino-qa-web`). Shared queues across platforms are prohibited.

**RULE SC-2**: Switching between local devices and cloud devices (BrowserStack or equivalent) MUST require only environment variable changes. Zero goal code changes, zero workflow changes. Any design that requires code changes to switch device targets violates this rule.

**RULE SC-3**: BrowserStack is the designated cloud device provider for scale. Connection is via standard Appium remote URL with basic auth (`BROWSERSTACK_USERNAME` + `BROWSERSTACK_ACCESS_KEY`). No BrowserStack-proprietary SDKs in goal or framework code.

**RULE SC-4**: Worker processes are stateless. All durable state (conversation history, workflow state, tool results) lives in Temporal. A worker can crash and restart without losing a test run in progress.

**RULE SC-5**: A goal MUST reference screen maps that exist for its platform before it can be merged to the main branch. A goal with missing screen map entries for its declared platform is incomplete.

### Framework Immutability Rules

**RULE FI-1**: The following files are permanently frozen. No feature spec may require modifications to them:
- `workflows/agent_goal_workflow.py`
- `activities/tool_activities.py`
- `shared/mcp_client_manager.py`
- `prompts/agent_prompt_generators.py`

**RULE FI-2**: Once a goal file is shipped in a released spec (e.g., `goals/slingo_qa.py` from spec-001), it is frozen. Subsequent specs add new goal files; they do not modify shipped goal files.

### Goal Design Rules

**RULE GD-1**: Goals are platform-specific. A goal MUST declare exactly one platform. There are no "universal" or "cross-platform" goals.

**RULE GD-2**: Every goal MUST declare its `mcp_server_definition`. A goal without an MCP server definition is not a valid casino QA goal.

**RULE GD-3**: The goal `description` is the sole source of domain knowledge for the LLM. Game rules, screen coordinates, QA instructions, edge case handling, and tool usage warnings MUST be in the description. They MUST NOT be scattered across workflow code, activities, or prompts.

**RULE GD-4**: A goal MUST specify `included_tools`. An empty or missing `included_tools` list means the MCP server exposes all tools to the LLM — this is prohibited for production goals (token cost and safety risk).

---

## Target Matrix

### Product Flavors
| Flavor | Description | Package Path |
|--------|-------------|-------------|
| **Sportsbook + Casino** | Combined app with casino as embedded feature | `com/betfanatics/shared/broker/sportsbook/casino` |
| **STAC** | Standalone Casino app | TBD — extract from Gradle config |

### Environments (`BUILD_ENV`)
| Value | Purpose | Automation Priority |
|-------|---------|-------------------|
| `dev` | Developer validation, internal QA | Low — unstable |
| `test` | Formal QA, regression | High — primary automation target |
| `cert` | Pre-prod, regulator/GLI certification | High — release gate |
| `prod-debug` | Production with debug capabilities | Medium — post-deploy validation |
| `prod` | Live production | Smoke tests only |

### Build Types (`BUILD_TYPE`)
| Value | Description |
|-------|-------------|
| `debug` | Debug build with extra logging, dev tools enabled |
| `release` | Production build, obfuscated, no debug tooling |

### Product Flavors (`PRODUCT_FLAVOR`)
| Value | Description |
|-------|-------------|
| `casino` | Standalone Casino app (STAC) |
| `sportsbook_casino` | Combined Sportsbook + Casino app |

### Platforms
| Platform | Status | MCP Tool Layer | Worker Host Constraint |
|----------|--------|---------------|----------------------|
| **Android** | Phase 1 demo (spec-001: mobile-mcp) / Phase 2 prod (spec-002: appium-mcp) | appium-mcp | macOS: outside Docker. Linux EC2: Docker with KVM |
| **iOS** | Phase 2 (spec-002) | appium-mcp | macOS only (local or EC2 Mac). Never Linux or Docker |
| **Web** | Phase 2 (spec-002) | @playwright/mcp | Docker-compatible. Any host |

### Jurisdictions
| State | RNG | Live Dealer | Notes |
|-------|-----|-------------|-------|
| New Jersey (NJ) | Yes | Yes | |
| Pennsylvania (PA) | Yes | Yes | State-specific RG UI requirements |
| Michigan (MI) | Yes | Yes | |
| West Virginia (WV) | Yes | No | RNG only |

All workflows must accept a `jurisdiction_code` parameter. State-specific behavior (RG prompts, available games, payment methods) is parameterized, not branched.

---

## Architecture

### Game Loading Model

Games load inside the Fanatics app as: **Native App -> WebView -> HTML Shell -> iframe (provider game URL)**

Provider communication uses `postMessage` between the WebView parent and the game iframe:
- `operator.ready` — FBG tells game it's ready
- `operator.game.session.end` — FBG closes game session
- `gel.ready` — Provider tells FBG game is loaded

The agent interacts with rendered pixels via mobile tools. It does not interact with the WebView or iframe directly. The agent sees what the user sees.

**Important**: On mobile, `mobile_list_elements_on_screen` and `appium_find_element` cannot see inside WebView/iframe game content. All in-game interactions must use coordinates derived from screenshots. This is a hard constraint encoded in every mobile goal description (Rule GD-3).

### Worker Topology

```
Your Mac (demo / local dev)
├── Android worker (outside Docker) ← appium-mcp → local emulator
├── iOS worker (outside Docker)     ← appium-mcp → Xcode Simulator
├── Web worker (in Docker or local) ← playwright-mcp → local browser
└── Docker
    ├── temporal
    ├── temporal-ui
    ├── api
    ├── frontend
    └── web-worker (optional — can run here)

Linux EC2 (staging / prod)
├── Docker
│   ├── temporal
│   ├── api
│   ├── android-worker (Docker + /dev/kvm) ← appium-mcp → emulator
│   └── web-worker ← playwright-mcp → headless browser
└── (iOS requires separate macOS EC2)

macOS EC2 (prod iOS)
└── ios-worker (native process) ← appium-mcp → BrowserStack or Simulator

BrowserStack (cloud scale)
├── Android devices ← Appium remote URL (basic auth)
├── iOS devices     ← Appium remote URL (basic auth)
└── Browsers        ← Playwright MCP remote
```

### Game Providers
FBG integrates 20+ providers across direct and aggregator channels:
- **Direct**: Evolution, IGT, Light & Wonder, Pariplay, Playtech, Boom Gaming, White Hat Studios, Games Global
- **Via L&W OGS**: Gaming Realms, Hacksaw, Konami, Relax Gaming, Wazdan, and 15+ others
- **Via Evolution**: NetEnt, Big Time Gaming, Red Tiger, No Limit City, Ezugi
- **Catalog**: 100-200 games per state, with new games launching monthly

### Backend Integration
- **RGI (Remote Gaming Interface)**: FBG's connector between game providers and the FBG wallet
- **RGS (Remote Gaming System)**: Provider-side game engines
- **Wallet**: FBG-owned, manages cash balance, casino credits, FanCash
- **GeoComply**: Geolocation tokens with TTL, cached in Redis via Kafka

### Screen Map Schema

```json
{
  "app": "fanatics_casino",
  "platform_screens": {
    "android": {
      "<resolution>": {
        "<screen_name>": {
          "visual_anchors": ["description of what identifies this screen"],
          "elements": {
            "<element_name>": {
              "x": 540,
              "y": 1780,
              "intent": "spin",
              "type": "button|input|region|text",
              "notes": "optional context"
            }
          },
          "last_verified": "2026-03-12",
          "device_verified": "Pixel_5_API_34"
        }
      }
    },
    "ios": {
      "<resolution>": { "...same structure..." }
    }
  },
  "game_screens": {
    "<game_id>": {
      "android": {
        "<resolution>": { "...same structure..." }
      },
      "ios": {
        "<resolution>": { "...same structure..." }
      }
    }
  }
}
```

Resolution is a secondary key under platform. Platform is the primary partition. Build version is tracked but does not partition coordinates (game UI does not change between builds).

---

## Goal Catalog

All goals use `AgentGoalWorkflow` (unchanged). Each goal = different tools + different MCP server + different LLM instructions.

### Platform Goals (Game-Agnostic)

| Goal ID | Platform | Tools | Description | Approval Required |
|---------|----------|-------|-------------|-------------------|
| `goal_casino_login` | Android/iOS | appium-mcp | Log into Fanatics Casino app | No |
| `goal_casino_deposit` | Android/iOS | appium-mcp | Execute a deposit flow | Yes |
| `goal_casino_withdraw` | Android/iOS | appium-mcp | Execute a withdrawal flow | Yes |
| `goal_casino_balance_check` | Android/iOS | appium-mcp | Read and report current balance | No |
| `goal_casino_search_game` | Android/iOS | appium-mcp | Search for a game by name | No |
| `goal_casino_apply_promo` | Android/iOS | appium-mcp | Apply a promotional code | Yes |
| `goal_casino_rg_check` | Android/iOS | appium-mcp | Test responsible gaming limits | No |
| `goal_casino_geo_check` | Android/iOS | appium-mcp | Test geolocation gating | No |

### Game Goals

| Goal ID | Platform | MCP Server | Description |
|---------|----------|-----------|-------------|
| `goal_slingo_qa` | Android (demo) | mobile-mcp (legacy) | spec-001: play one round via mobile-mcp |
| `goal_slingo_qa_android` | Android | appium-mcp | spec-002: play one round via Appium |
| `goal_slingo_qa_ios` | iOS | appium-mcp | spec-002: play one round on iOS |
| `goal_slingo_qa_web` | Web | @playwright/mcp | spec-002: play one round in browser |

### Future Integration: SlotBot

SlotBot is an internal Java/Kotlin library (built by a colleague) that uses OpenCV image template matching and a YAML-configured state machine for **deterministic** game automation. It is architecturally complementary to this AI agent:

- **SlotBot** = automated player (knows exactly what state to expect, clicks accordingly)
- **This agent** = AI QA tester (observes, decides, detects anomalies, reports like a human)

**Future integration path**: Expose SlotBot's game state detection (`getState()`) as a callable MCP tool or Temporal activity. The LLM receives a structured state label (`"state": "wild_selection"`) instead of reasoning about it purely from screenshots. This would improve state detection reliability for complex in-game scenarios.

**Not in scope** for spec-001 or spec-002. Requires a dedicated spec and Java/Python interop design.

### Test Suite Composition (Future — via multi-goal mode or orchestrator)

| Suite | Goals Chained | When To Run |
|-------|---------------|-------------|
| Smoke Test | login -> balance -> slingo round -> balance -> done | Post-deploy, nightly |
| Regression | login -> all game goals -> all platform goals -> done | Pre-release in TEST/CERT |
| New Build | (install APK) -> smoke test | On every build cut |
| Promo Test | login -> apply promo -> play required game -> verify | When promos configured |

---

## Test Report Schema

```json
{
  "test_id": "slingo-qa-2026-03-12-001",
  "suite": "smoke_test",
  "workflow_id": "temporal-workflow-xyz",
  "environment": "test",
  "jurisdiction": "NJ",
  "device": {
    "name": "Pixel_5_API_34",
    "platform": "android",
    "resolution": "1080x1920",
    "os_version": "14",
    "source": "local|browserstack"
  },
  "app": {
    "flavor": "stac",
    "build": "8.3.0",
    "build_number": "2603121200"
  },
  "game": "slingo_cash_eruption",
  "results": {
    "starting_balance": { "cash": 50.00, "credits": 0.00, "fancash": 5.00 },
    "ending_balance": { "cash": 49.20, "credits": 0.00, "fancash": 5.00 },
    "balance_delta": -0.80,
    "bet_amount": 0.20,
    "spins_played": 5,
    "extra_spins_purchased": 0,
    "slingos_achieved": 2,
    "bonus_triggered": false,
    "wilds_encountered": 1,
    "super_wilds_encountered": 0
  },
  "timing": {
    "total_seconds": 185,
    "login_seconds": 12,
    "navigation_seconds": 8,
    "gameplay_seconds": 155,
    "report_seconds": 10
  },
  "screenshots": [
    { "phase": "pre_game", "path": "screenshots/001_balance.png" },
    { "phase": "spin_1", "path": "screenshots/002_spin1.png" },
    { "phase": "post_game", "path": "screenshots/010_final.png" }
  ],
  "anomalies": [],
  "status": "PASS",
  "p0_journey_ref": "Game Launch & Gameplay",
  "jira_test_case_ref": null
}
```

---

## Known Bug Patterns (Agent Must Watch For)

| Pattern | Detection Method | Jira Refs |
|---------|-----------------|-----------|
| Casino credits not reflected in-game | Vision: read balance, compare cash vs credits displayed | OLY-885, VLAD-443, ICG-2761 |
| Free spins promo reusable when it shouldn't be | Workflow: attempt promo twice, verify rejection | SHOCK-2421 |
| Session logout after extended gameplay | Workflow: play 15+ min, verify session alive | WEB-888 |
| FanCash conversion not reflected until restart | Workflow: convert FanCash, verify balance without restarting | OGX-3288 |
| Casino tile spacing/layout breaks | Vision: detect UI anomalies on home screen | ICG-2601, ICG-2637 |
| Transaction records show $0.00 for credits | Proxyman (Phase 2): validate API response amounts | VLAD-593 |

---

## CI/CD Integration

- **Build source**: Bitrise (migrated from GitHub Actions)
- **Artifact retrieval**: Bitrise API with workspace access token
- **Build workflows**: `android-cd-casino-test`, `android-cd-casino-cert`, `ios-cd-casino-test`, etc.
- **Release pipeline**: `cut-mobile-release` produces 12 builds (3 envs x 2 flavors x 2 platforms)
- **Distribution**: TestFlight (iOS), internal testing track (Android)
- **Agent trigger point**: On build artifact availability, pull APK/IPA, install on device, run smoke test

---

## P0 Journey Coverage Map

| P0 Journey | Workflow(s) | Priority |
|------------|-------------|----------|
| App Launch & Lobby Load | `LoginWorkflow` + `CheckBalanceWorkflow` | Critical |
| Game Launch & Gameplay | `NavigateToGameWorkflow` + `PlayRoundWorkflow` | Critical |
| Deposit Flows | `DepositWorkflow` | Critical |
| Withdrawal Flow | `WithdrawWorkflow` | Critical |
| Balance Display & Updates | `CheckBalanceWorkflow` (before/after play) | Critical |
| Free Spins Lifecycle | `ApplyPromoWorkflow` + `PlayRoundWorkflow` | High |
| Responsible Gaming Enforcement | `ResponsibleGamingWorkflow` | Critical |
| State & Compliance Gating | `GeolocationCheckWorkflow` | Critical |
| FanCash Jackpots | Dedicated workflow (Phase 2) | Medium |
| Daily Spin | Dedicated workflow (Phase 2) | Medium |

---

## Configuration

### Environment Variables

```
# Device — local
ANDROID_SERIAL=emulator-5554
IOS_UDID=                          # Simulator UDID from `xcrun simctl list`
DEVICE_RESOLUTION=1080x1920

# Device — BrowserStack (optional, overrides local)
BROWSERSTACK_USERNAME=
BROWSERSTACK_ACCESS_KEY=
BROWSERSTACK_APPIUM_URL=https://hub.browserstack.com/wd/hub

# App
PRODUCT_FLAVOR=casino              # casino | sportsbook_casino
BUILD_ENV=dev                      # dev | test | cert | prod-debug | prod
BUILD_TYPE=debug                   # debug | release
PLATFORM=android                   # android | ios | web — drives worker task queue selection
APP_PACKAGE=com.betfanatics.casino # Android package name
APP_BUNDLE_ID=com.betfanatics.casino # iOS bundle ID
JURISDICTION=NJ                    # NJ | PA | MI | WV

# LLM
LLM_MODEL=openai/gpt-4o
LLM_KEY=sk-...
VISION_LLM_MODEL=anthropic/claude-sonnet-4-20250514
VISION_LLM_KEY=sk-ant-...

# Test Accounts
TEST_EMAIL=qa-agent@betfanatics.com
TEST_PASSWORD=...

# Temporal — per platform worker
TEMPORAL_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=casino-qa-android  # casino-qa-android | casino-qa-ios | casino-qa-web

# Goal
AGENT_GOAL=goal_slingo_qa_android

# MCP Servers (Phase 2)
# PROXYMAN_API_URL=http://localhost:9090
# LAUNCHDARKLY_SDK_KEY=...

# Build Retrieval
# BITRISE_ACCESS_TOKEN=...
# BITRISE_APP_SLUG=...
```

---

## File Structure

Existing files are unchanged. We only add new files:

```
casino-slingo-testing-agent/
  goals/
    slingo_qa.py                    # spec-001 FROZEN — mobile-mcp, Android demo
    slingo_qa_android.py            # spec-002 NEW — appium-mcp, Android
    slingo_qa_ios.py                # spec-002 NEW — appium-mcp, iOS
    slingo_qa_web.py                # spec-002 NEW — playwright-mcp, Web
    __init__.py                     # EDIT — add spec-002 goal imports
  shared/
    mcp_config.py                   # EDIT — add appium + playwright server definitions
  screen_maps/
    platform/
      android/
        1080x1920.json              # EXISTS (spec-001) — platform UI coords
      ios/
        <resolution>.json           # spec-002 NEW
    games/
      slingo_cash_eruption/
        android/
          1080x1920.json            # EXISTS (spec-001) — game coords
        ios/
          <resolution>.json         # spec-002 NEW
  scripts/
    run_worker_android.py           # spec-002 NEW — android worker entry point
    run_worker_ios.py               # spec-002 NEW — ios worker entry point
    run_worker_web.py               # spec-002 NEW — web worker entry point

  # PERMANENTLY FROZEN:
  workflows/agent_goal_workflow.py
  activities/tool_activities.py
  shared/mcp_client_manager.py
  prompts/agent_prompt_generators.py
  api/main.py
```

---

## Governance

- This constitution is the single source of truth for all architectural decisions
- Hard Rules (PT, MCP, SC, FI, GD sections) override any conflicting spec requirement
- New specs must be validated against all Hard Rules before `/speckit.plan` is invoked
- New test scenarios = new goal files, never new workflows or activities
- All device interaction goes through the designated MCP server for that platform (Rule MCP-1, MCP-2)
- Screen maps are append-only in production; platform is the primary partition (Rule SC-5)
- P0 journey coverage is the acceptance criteria — every P0 must have a corresponding goal on every supported platform
- New games follow the same pattern: one goal file per platform, game rules in description
- SlotBot is a future integration candidate, not in scope until explicitly specced
- Constitution amendments require documentation of what changed and why

**Version**: 2.0.0 | **Ratified**: 2026-03-12 | **Last Amended**: 2026-03-12
**Changes from v1.0.0**: Added Hard Rules section (PT, MCP, SC, FI, GD), updated platform matrix to include Appium/Playwright, updated screen map schema with platform partitioning, updated goal catalog with spec-002 goals, added SlotBot as future integration candidate, updated worker topology diagram, added per-platform task queue naming convention.
