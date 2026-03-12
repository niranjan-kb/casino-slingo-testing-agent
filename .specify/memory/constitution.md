# Fanatics Casino QA Agent Constitution

## Identity

This project is an AI-powered QA testing agent for the **Fanatics Casino** mobile and web applications, built by **Fanatics Betting & Gaming (FBG)**. FBG is a casino operator, not a game studio. We test our app as a platform — game engines are owned by providers (Gaming Realms, Evolution, IGT, Light & Wonder, etc.). Our concern is: does our app correctly wrap, launch, settle, and account for every game across every device, environment, and jurisdiction?

## Core Principles

### I. Same Architecture, New Goal — The LLM Is the Brain

We do NOT build new workflows or modify `AgentGoalWorkflow`. The existing agent loop is unchanged. We add a new **goal** (`goal_slingo_qa`) that uses **mobile-mcp tools** instead of Stripe/flight/HR tools. The LLM decides every action:

1. LLM receives: goal description + tools list + conversation history (including screenshot results)
2. LLM responds: `{ "next": "confirm", "tool": "mobile_take_screenshot", "args": {"device": "emulator-5554"} }`
3. User confirms (or auto-confirms if `SHOW_CONFIRM=False`)
4. Tool executes as Temporal activity via `mcp_tool_activity`
5. Result goes back into conversation history
6. LLM sees result, decides next tool — LOOP
7. When done: `"next": "done"`, returns test report

The goal description encodes all domain knowledge (game rules, screen map coordinates, QA instructions). The LLM uses this to make good decisions about what to tap, when to screenshot, how to handle wilds, and when the round is over. Each mobile-mcp tool (`mobile_take_screenshot`, `mobile_click_on_screen_at_coordinates`, `mobile_swipe_on_screen`, `mobile_type_keys`, `mobile_press_button`, `mobile_list_elements_on_screen`, `mobile_launch_app`) is a tool the LLM can call — just like `customers.read` or `create_invoice` in the Stripe goal.

See [example-goal-workflows-activities-signals.md](example-goal-workflows-activities-signals.md) for the full sequence diagram.

### II. Every Device/External Interaction Is an MCP Call

All interaction with the device, network proxy, and feature flag systems goes through MCP servers:

- **mobile-mcp**: screenshot, tap, swipe, type_text, press_button (via ADB/XCUITest)
- **proxyman-mcp** (Phase 2): inspect HTTP requests, validate API contracts
- **launchdarkly-mcp** (Phase 2): read/toggle feature flags per environment

No direct ADB commands in workflow code. No subprocess calls to device tools. MCP is the only interface to the outside world. Temporal activities wrap MCP tool calls for durability and retry.

### III. Screen Map Is Domain Knowledge in the Prompt

The screen map is a structured JSON knowledge base keyed by resolution. It is loaded into the **goal description** so the LLM has coordinate knowledge when deciding where to tap.

- LLM sees screenshot + screen map coordinates in its prompt context
- For known screens/resolutions: LLM references map coordinates directly in tool args
- For unknown screens: LLM uses vision to determine coordinates, and the map is updated
- Game UI rarely changes between builds — device resolution is the variable

The screen map saves tokens over time. Without it, the LLM must reason about coordinates from every screenshot. With it, the LLM can reference known coordinates and only fall back to visual reasoning on new screens or resolutions.

### IV. One Goal Per Test Scenario, Composable via Goal Switching

Each test scenario (Slingo round, deposit flow, responsible gaming check) is a separate **goal** — not a separate workflow. `AgentGoalWorkflow` is the only workflow. Goals can chain by using the existing `ChangeGoal` tool to switch to the next goal when one completes.

- `goal_slingo_qa` — play one round of Slingo, report balance change
- `goal_casino_login` — log into the Fanatics Casino app
- `goal_casino_deposit` — execute a deposit flow
- `goal_casino_rg_check` — test responsible gaming limits

Each goal has its own tools, description, and example conversation history. The LLM drives each one using the same agent loop. For full test suites, a parent orchestrator (or multi-goal mode) chains goals in sequence.

### V. Adding a New Game = Adding a New Goal

Adding a new game means:
1. Write a new goal file (e.g., `goals/blackjack_qa.py`) with game rules in the description
2. Add screen map entries for the game's UI elements
3. Register the goal in `goals/__init__.py`

The goal description encodes the game's state machine, decision points, and visual cues. The mobile-mcp tools are shared across all games. No new workflows, activities, or tools needed.

### VI. Human Approval at Financial Boundaries

The agent requires human confirmation before:
- Placing a bet (confirms amount)
- Purchasing extra spins (costs money)
- Making deposits or withdrawals
- Applying promotional codes
- Any action that spends real or bonus funds

Autonomous actions (navigation, screenshots, screen reading, tapping non-financial UI) proceed without approval.

## Target Matrix

### Product Flavors
| Flavor | Description | Package Path |
|--------|-------------|-------------|
| **Sportsbook + Casino** | Combined app with casino as embedded feature | `com/betfanatics/shared/broker/sportsbook/casino` |
| **STAC** | Standalone Casino app | TBD — extract from Gradle config |

### Environments
| Environment | Purpose | Automation Priority |
|-------------|---------|-------------------|
| `dev` | Developer validation, internal QA | Low — unstable |
| `test` | Formal QA, regression | High — primary automation target |
| `cert` | Pre-prod, regulator/GLI certification | High — release gate |
| `prod-debug` | Production with debug capabilities | Medium — post-deploy validation |
| `prod` | Live production | Smoke tests only |

### Platforms (Build Order)
| Platform | Status | MCP Transport |
|----------|--------|--------------|
| **Android** | Phase 1 — start here | mobile-mcp via ADB |
| **iOS** | Phase 2 | mobile-mcp via XCUITest |
| **Web** | Phase 3 | browser-mcp or Playwright MCP |

### Jurisdictions
| State | RNG | Live Dealer | Notes |
|-------|-----|-------------|-------|
| New Jersey (NJ) | Yes | Yes | |
| Pennsylvania (PA) | Yes | Yes | State-specific RG UI requirements |
| Michigan (MI) | Yes | Yes | |
| West Virginia (WV) | Yes | No | RNG only |

All workflows must accept a `jurisdiction_code` parameter. State-specific behavior (RG prompts, available games, payment methods) is parameterized, not branched.

## Architecture

### Game Loading Model

Games load inside the Fanatics app as: **Native App -> WebView -> HTML Shell -> iframe (provider game URL)**

Provider communication uses `postMessage` between the WebView parent and the game iframe:
- `operator.ready` — FBG tells game it's ready
- `operator.game.session.end` — FBG closes game session
- `gel.ready` — Provider tells FBG game is loaded

The agent interacts with the rendered pixels via mobile-mcp. It does not interact with the WebView or iframe directly. The agent sees what the user sees.

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
  "game_screens": {
    "<game_id>": {
      "<resolution>": {
        "<screen_name>": { "...same structure..." }
      }
    }
  }
}
```

Resolution is the primary key. Build version is tracked but does not partition coordinates (game UI does not change between builds; resolution does).

## Goal Catalog

All goals use `AgentGoalWorkflow` (unchanged). Each goal = different tools + different LLM instructions.

### Platform Goals (Game-Agnostic)

| Goal ID | Tools | Description | Approval Required |
|---------|-------|-------------|-------------------|
| `goal_casino_login` | mobile-mcp | Log into Fanatics Casino app | No |
| `goal_casino_deposit` | mobile-mcp | Execute a deposit flow | Yes |
| `goal_casino_withdraw` | mobile-mcp | Execute a withdrawal flow | Yes |
| `goal_casino_balance_check` | mobile-mcp | Read and report current balance | No |
| `goal_casino_search_game` | mobile-mcp | Search for a game by name | No |
| `goal_casino_apply_promo` | mobile-mcp | Apply a promotional code | Yes |
| `goal_casino_rg_check` | mobile-mcp | Test responsible gaming limits | No |
| `goal_casino_geo_check` | mobile-mcp | Test geolocation gating | No |

### Game Goals (First Game: Slingo Cash Eruption)

| Goal ID | Tools | Description |
|---------|-------|-------------|
| `goal_slingo_qa` | mobile-mcp | Play one full round of Slingo Cash Eruption, report balance change |

The goal description for `goal_slingo_qa` encodes:
- Game rules (5 base spins, wilds, super wilds, fireballs, extra spins phase)
- Screen map coordinates for the current resolution
- QA instructions (always tap END GAME during extra spins, read balance before/after)
- Visual cues (what each symbol looks like, how to identify game states)

The LLM follows this knowledge to decide the sequence:
screenshot -> read balance -> tap spin -> screenshot -> handle result -> ... -> end game -> read final balance -> report

### Test Suite Composition (Future — via multi-goal mode or orchestrator)

| Suite | Goals Chained | When To Run |
|-------|---------------|-------------|
| Smoke Test | login -> balance -> slingo round -> balance -> done | Post-deploy, nightly |
| Regression | login -> all game goals -> all platform goals -> done | Pre-release in TEST/CERT |
| New Build | (install APK) -> smoke test | On every build cut |
| Promo Test | login -> apply promo -> play required game -> verify | When promos configured |

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
    "os_version": "14"
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

## Known Bug Patterns (Agent Must Watch For)

These are recurring issues from recent Jira history. The agent should actively detect these:

| Pattern | Detection Method | Jira Refs |
|---------|-----------------|-----------|
| Casino credits not reflected in-game | Vision: read balance, compare cash vs credits displayed | OLY-885, VLAD-443, ICG-2761 |
| Free spins promo reusable when it shouldn't be | Workflow: attempt promo twice, verify rejection | SHOCK-2421 |
| Session logout after extended gameplay | Workflow: play 15+ min, verify session alive | WEB-888 |
| FanCash conversion not reflected until restart | Workflow: convert FanCash, verify balance without restarting | OGX-3288 |
| Casino tile spacing/layout breaks | Vision: detect UI anomalies on home screen | ICG-2601, ICG-2637 |
| Transaction records show $0.00 for credits | Proxyman (Phase 2): validate API response amounts | VLAD-593 |

## CI/CD Integration

- **Build source**: Bitrise (migrated from GitHub Actions)
- **Artifact retrieval**: Bitrise API with workspace access token
- **Build workflows**: `android-cd-casino-test`, `android-cd-casino-cert`, `ios-cd-casino-test`, etc.
- **Release pipeline**: `cut-mobile-release` produces 12 builds (3 envs x 2 flavors x 2 platforms)
- **Distribution**: TestFlight (iOS), internal testing track (Android)
- **Agent trigger point**: On build artifact availability, pull APK, install on device, run smoke test

## P0 Journey Coverage Map

The agent's test coverage maps directly to the iCasino P0 User Journeys document. Each P0 journey becomes one or more workflows:

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

## Configuration

### Environment Variables

```
# Device
ANDROID_SERIAL=emulator-5554
DEVICE_RESOLUTION=1080x1920

# App
APP_FLAVOR=stac                    # stac | sportsbook_casino
APP_ENVIRONMENT=test               # dev | test | cert | prod-debug | prod
APP_PACKAGE=com.betfanatics.casino # TBD - confirm from Gradle
JURISDICTION=NJ                    # NJ | PA | MI | WV

# LLM (text/planning)
LLM_MODEL=openai/gpt-4o
LLM_KEY=sk-...

# LLM (vision/screenshots)
VISION_LLM_MODEL=anthropic/claude-sonnet-4-20250514
VISION_LLM_KEY=sk-ant-...

# Test Accounts
TEST_EMAIL=qa-agent@betfanatics.com
TEST_PASSWORD=...

# MCP Servers (Phase 2)
# PROXYMAN_API_URL=http://localhost:9090
# LAUNCHDARKLY_SDK_KEY=...

# Temporal
TEMPORAL_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=casino-qa-agent

# Build Retrieval
# BITRISE_ACCESS_TOKEN=...
# BITRISE_APP_SLUG=...
```

## File Structure (What We Add)

Existing files are unchanged. We only add new files:

```
casino-slingo-testing-agent/
  goals/
    slingo_qa.py               # NEW - goal definition for Slingo QA
    __init__.py                 # EDIT - add import for slingo_qa_goals
  shared/
    mcp_config.py              # EDIT - add get_mobile_mcp_server_definition()
  screen_maps/
    platform/
      1080x1920.json           # NEW - platform UI coordinates
    games/
      slingo_cash_eruption/
        1080x1920.json         # NEW - game-specific coordinates
  the_game.md                  # EXISTS - game rules (referenced in goal description)

  # Everything below is UNCHANGED:
  workflows/agent_goal_workflow.py   # no changes
  activities/tool_activities.py      # no changes (mcp_tool_activity already exists)
  shared/mcp_client_manager.py       # no changes
  models/tool_definitions.py         # no changes
  prompts/agent_prompt_generators.py # no changes
  api/main.py                        # no changes
  frontend/                          # no changes (maybe render screenshots)
```

## Governance

- This constitution is the single source of truth for architectural decisions
- We use the existing `AgentGoalWorkflow` — never modify it for casino-specific logic
- New test scenarios = new goals, not new workflows or activities
- All device interaction goes through mobile-mcp tools via `mcp_tool_activity`
- Screen map is append-only in production (new resolutions added, existing never deleted without review)
- P0 journey coverage is the acceptance criteria — every P0 must have a corresponding goal
- New games follow the same pattern: new goal file with game rules in description
- Constitution amendments require documentation of what changed and why

**Version**: 1.0.0 | **Ratified**: 2026-03-12 | **Last Amended**: 2026-03-12
