# Fanatics Casino QA Agent

An AI-powered QA testing agent for the Fanatics Casino mobile app. The agent uses an LLM to see the screen, decide what to do, and interact with a real Android device via [mobile-mcp](https://github.com/mobile-next/mobile-mcp) — all orchestrated durably by Temporal.

Built on the [Temporal AI Agent](https://github.com/temporalio/temporal-ai-agent) framework. Same `AgentGoalWorkflow`, same chat UI, same tool approval pattern — just pointed at a mobile device instead of Stripe or a flight API.

## What It Does

The agent plays casino games on the Fanatics Casino app and reports results. The first game is **Slingo Cash Eruption**. A typical test run:

1. Launch the app on an Android emulator
2. Log in with test credentials
3. Search for and open the game
4. Record starting balance
5. Play one full round (5 spins, handle wilds, end game)
6. Record ending balance, report the delta

The LLM decides every action: what to screenshot, where to tap, how to handle game events. Device interaction happens through mobile-mcp tools (`mobile_take_screenshot`, `mobile_click_on_screen_at_coordinates`, `mobile_type_keys`, etc.) executed as Temporal activities.

## Why This Approach

FBG is a casino **operator**, not a game studio. Game engines are owned by providers (Gaming Realms, Evolution, IGT, etc.). We test our **app as a platform** — does it correctly wrap, launch, settle, and account for every game?

This agent replaces the QA engineer who sits with a phone and plays games before a release. It runs continuously, logs every state transition with screenshots, and scales to N devices in parallel.

## Target Matrix

| Dimension | Values |
|-----------|--------|
| **Flavors** | Sportsbook + Casino (combined), STAC (standalone casino) |
| **Environments** | dev, test, cert, prod-debug, prod |
| **Platforms** | Android (Phase 1), iOS (Phase 2), Web (Phase 3) |
| **Jurisdictions** | NJ, PA, MI, WV |

## Architecture

Same architecture as the base Temporal AI Agent — no modifications to the workflow or activities:

```
Frontend (:5173) --> FastAPI (:8000) --> Temporal Workflow
                                              |
                                    AgentGoalWorkflow (unchanged)
                                              |
                            LLM decides --> MCP tool executes --> result back to LLM
                                              |
                                    mobile-mcp (via ADB)
                                              |
                                    Android Emulator / Device
```

The LLM is the brain. mobile-mcp is the hands. Temporal is the guarantee that nothing gets lost.

See [architecture guide](docs/architecture.md) for the base framework and [constitution](.specify/memory/constitution.md) for casino-specific design decisions.

## Quick Start

### Prerequisites

- Android emulator running (or real device via ADB)
- `adb devices` shows your device
- Node.js v22+ (for mobile-mcp)
- Temporal dev server (`temporal server start-dev`)

### Run

```bash
# 1. Install dependencies
uv sync

# 2. Configure .env (see below)
cp .env.example .env

# 3. Start the worker + API + frontend
make run-worker    # terminal 1
make run-api       # terminal 2
make run-frontend  # terminal 3
```

Open http://localhost:5173 and type "Start the QA test".

### Configuration

```bash
# .env — the key settings
AGENT_GOAL=goal_slingo_qa
LLM_MODEL=bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
AWS_PROFILE=bedrock
AWS_REGION_NAME=us-east-1
SHOW_CONFIRM=True
GOAL_CATEGORIES=casino-qa
```

## Project Structure (What We Added)

```
goals/
  slingo_qa.py           # Goal: play Slingo Cash Eruption, report results
  __init__.py             # Updated to register casino-qa goals
shared/
  mcp_config.py           # Updated with mobile-mcp server definition
screen_maps/              # Coordinate knowledge base by resolution
  games/slingo_cash_eruption/
the_game.md               # Slingo Cash Eruption game rules & visual cues
```

Everything else (workflows, activities, models, frontend) is unchanged from the base framework.

## Key Documents

| Document | Purpose |
|----------|---------|
| [Constitution](.specify/memory/constitution.md) | Core principles, target matrix, goal catalog, architecture decisions |
| [Example Flow](example-goal-workflows-activities-signals.md) | Sequence diagram: agent loop mapped to mobile-mcp tool calls |
| [Game Rules](the_game.md) | Slingo Cash Eruption mechanics, symbols, UI layout, coordinate reference |
| [Rovo Research](rovo-simple-research.md) | FBG internal context: app architecture, QA process, known bugs |

## Testing

```bash
uv sync
uv run pytest
uv run pytest --workflow-environment=time-skipping
```

See [testing guide](docs/testing.md) for details.

## Roadmap

- **Phase 1** (now): Slingo Cash Eruption on Android emulator, single game, balance tracking
- **Phase 2**: proxyman-mcp (network validation), launchdarkly-mcp (feature flags), iOS support
- **Phase 3**: Multi-game coverage (100+ games), AWS Device Farm, CI/CD integration via Bitrise
