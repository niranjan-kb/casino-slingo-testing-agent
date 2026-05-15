# Fanatics Casino QA Agent — Danny Ocean

An AI **casino game player** named **Danny Ocean** that plays Fanatics Casino games end-to-end on real Android devices and reports anything that looks broken — like a real player would, but never sleeps. Built on **Temporal** for visibility (every screen, every tap, every decision is a workflow event in the Temporal UI) and durability (worker crashes mid-spin replay to the exact step).

> *"Winning isn't the end. It's just the buy-in for the next hand."* — Danny Ocean

Player-first, QA-aware. The agent doesn't pretend to be a tester — it plays the games, observes outcomes, and reports anything that feels off. The QA report falls out of the play session as a side effect.

## What it does

```
asked for a game → log in → navigate the lobby → search/find the game → play → report
```

Each phase is a discrete capability the agent composes at runtime. **One persona, three to four goals:**

| Layer | What it is |
|---|---|
| **`goal_casino_session`** ✅ | The session profile: tool list (Appium-MCP + screen-map DB tools), MCP server, starter prompt. One goal per workflow. Platform-agnostic; build/platform/resolution live in the screen-map DB. |
| **`intent_authenticate`** ✅ | LLM's per-turn objective: launch app → dismiss permission modals → Fanatics ONE 2-step (email → password → OTP) → confirm logged-in home. Locked. |
| **`intent_navigate_to_screen`** 🆕 | Per-turn objective: from any logged-in screen, reach a target screen (typically a game's loaded signature) via search / category / recents. |
| **`intent_play_game`** 🆕 | Per-turn objective: generic spin/play loop driven by `game_catalog.play_loop_json`. No per-game code. |
| **`intent_report`** 🆕 | Per-turn objective: write `reports/YYYY-MM-DD-<run>.md`. Session terminator. |

The persona (SOUL) is shared. The goal sets up infrastructure once; intents drive what the LLM is doing right now and can switch turn-to-turn.

## Why we test as a platform

FBG is a casino **operator**, not a game studio. Game engines are owned by providers (Gaming Realms, Evolution, IGT, etc.). We test our **app as a platform** — does it correctly wrap, launch, settle, and account for every game?

This agent replaces the QA engineer who sits with a phone before a release, plays games, and writes a report. It runs continuously, logs every state transition with screenshots, and scales to N devices in parallel.

## Why Temporal

- **Visibility** — every workflow event is a record in the Temporal UI at `localhost:8080`. Live debug feed for any in-flight session.
- **Durability** — a worker crash mid-spin replays to the exact step. Progress through a 5-spin round is never lost.
- **Idempotency** — transient MCP/Bedrock blips heal automatically via retry policies.
- **Audit trail** — conversation history is a workflow query; no separate database.

## Architecture

```
Frontend (:5173) ── FastAPI (:8000) ── Temporal Workflow ── LLM (Bedrock Anthropic)
                                              │                     │
                                       AgentGoalWorkflow ────────────┘
                                              │
                                    appium-mcp (SSE :3100)
                                              │
                                    Android emulator / device
```

The LLM is the brain. appium-mcp is the hands. Temporal is the guarantee that nothing gets lost. The agent's persona is in [`prompts/persona/soul.md`](prompts/persona/soul.md), mirrored from the canonical [SOUL.md](../casino-game-player/SOUL.MD).

Output structure is enforced by Anthropic **tool-use forcing** on a synthetic `plan_next_action` tool — the model literally cannot emit malformed JSON or hallucinate tool names that aren't in the goal's enum.

## Target matrix

| Dimension | Values |
|-----------|--------|
| **Flavors** | Sportsbook + Casino (combined), STAC (standalone casino) |
| **Environments** | dev, test, cert, prod-debug, prod |
| **Platforms** | Android (Phase 1), iOS (Phase 2), Web (Phase 3) |
| **Jurisdictions** | NJ, PA, MI, WV |

## Quick start

### Prerequisites
- Android emulator running, `adb devices` shows it
- Node.js v22+ (for `appium-mcp@1.56.3`)
- Docker (Temporal, Postgres, API, frontend)
- AWS SSO access to Bedrock (`aws sso login --profile bedrock`)
- `uv` (Python package manager)

### Run

```bash
# 1. Infrastructure
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend -d

# 2. Persistent appium-mcp SSE — PINNED to 1.56.3, newer breaks tool names
ANDROID_HOME=$ANDROID_HOME npx -y appium-mcp@1.56.3 --httpStream --port=3100

# 3. Android worker
PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py
```

Then either drive via the chat UI at `http://localhost:5173`, or via API:

```bash
curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=login'
```

Watch live in the Temporal UI: `http://localhost:8080`.

### Smoke test

```bash
uv run scripts/smoke_login.py --timeout 300
```

Resets the app, runs `goal_casino_session` against `intent_authenticate`, asserts `LOGIN PASS` lands within the timeout. Exits 0 on success.

### Configuration

`.env` essentials:

```bash
# Casino QA
AGENT_GOAL=goal_casino_session
TEMPORAL_TASK_QUEUE=casino-qa-android
PLATFORM=android
ANDROID_SERIAL=emulator-5554
DEVICE_RESOLUTION=1344x2992
BUILD_ENV=test            # → app package becomes com.betfanatics.casino.test
DEFAULT_OTP=864408        # auto-OTP used in dev/test
APPIUM_MCP_SSE_URL=http://localhost:3100/sse

# LLM (AWS Bedrock via SSO)
LLM_MODEL=bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
AWS_PROFILE=bedrock
AWS_REGION_NAME=us-east-1

# Test credentials (test build only — never check real creds in)
TEST_EMAIL=...
TEST_PASSWORD=...
```

## Roadmap

- **Phase 1** (now): goal_casino_session + intent_authenticate locked; intent_navigate_to_screen and intent_play_game in progress; single Slingo game on Android emulator
- **Phase 2**: Multi-game coverage (slots, blackjack, roulette), iOS support, proxyman-mcp for network validation, launchdarkly-mcp for feature-flag control
- **Phase 3**: 100+ games, AWS Device Farm, CI/CD via Bitrise, web platform support

## Where to read next

| Doc | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Full engineering guide. Architecture, gotchas, recipe for adding goals. **Start here if you're contributing code.** |
| [`prompts/persona/soul.md`](prompts/persona/soul.md) | The agent's runtime identity (mirror of the canonical SOUL.md). |
| [Constitution](.specify/memory/constitution.md) | Casino QA architecture decisions and target matrix |
| [`.claude/skills/mobile-goal-dev/SKILL.md`](.claude/skills/mobile-goal-dev/SKILL.md) | Recipe for adding a new capability goal |
