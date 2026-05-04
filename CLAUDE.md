# Casino QA Agent — Engineering Guide

Last updated: 2026-05-04

> **Project doctrine.** This file is the single source of truth for both AI agents (Claude Code, Codex, etc.) and human contributors. The `AGENTS.md` file is a pointer to this one. The agent's runtime persona is defined in `prompts/persona/soul.md`, mirrored from the canonical [SOUL.md](../casino-game-player/SOUL.MD) we maintain. This file describes how the *engineering system* around that persona works.

## What this is

An AI **casino game player** that happens to be an agent. It plays Fanatics Casino games on real devices/emulators end-to-end — log in, navigate the lobby, place bets, react to outcomes, exit safely, write a session report — and flags anything that looks broken along the way. **Player-first, QA-aware.**

The system is built on top of the [Temporal AI Agent](https://github.com/temporal-community/temporal-ai-agent) framework, with all the upstream's generic-platform scaffolding stripped out and replaced by casino-domain capabilities. We chose **Temporal as the spine** for visibility and durability: every screen, every tap, every LLM decision is a workflow event, recorded, replayable, and inspectable in the Temporal UI. A worker crash mid-spin replays to the exact step.

## The agent's mental model — one persona, three to four goals

The persona (SOUL) is shared. The agent composes capability-goals at runtime:

| Goal id | What it does | Status |
|---|---|---|
| **`goal_login`** | Authenticate end-to-end: launch app → dismiss permission modals → Fanatics ONE 2-step login (email → password) → OTP → confirm logged-in home/lobby. Platform-agnostic. | ✅ Locked 2026-04-29 |
| **`goal_navigate_to_game`** | From logged-in home, find a named game (search bar, category browse, recent), open it, dismiss any pre-game prompts (FanCash, location), wait for the WebView to load. | 🔜 Next |
| **`goal_play_game`** | Generic game loop: read starting balance → set stake → take N actions (spin/tap/decide) per the game's screen-map → handle special states → ensure safe exit. Parameterised by `game_name`. | 🔜 |
| **`goal_session_report`** | Write a markdown session report to `reports/YYYY-MM-DD-{game}-{run_id}.md` with bug list, balance ledger, observations, screen-map updates. | ✅ writer ready, not yet a goal |

Goals are **platform-agnostic capabilities**. Platform / build / resolution differences live in the screen-map DB (`data/screen_map.db`), never in goal names.

## Why Temporal

- **Visibility.** Every workflow event — every LLM call, every tool dispatch, every signal — is a record in Temporal. The Temporal UI at `localhost:8080` is the live debug feed for any in-flight session.
- **Durability.** A worker crash mid-spin replays to the exact step. The agent's progress through a 5-spin round is never lost.
- **Idempotency.** Activities have `RetryPolicy` configured so transient MCP/Bedrock blips heal automatically.
- **Audit trail.** Conversation history is persisted as a workflow query — no separate database needed.

## Active stack

- **Python 3.10** via `uv` (existing `.venv`)
- **Temporal SDK** — durable workflow spine (`agent-workflow` workflow id)
- **LiteLLM** → Bedrock (`claude-sonnet-4-5` today; bump to Opus when the exact Bedrock model id is confirmed) via AWS SSO
- **FastAPI** (`api/main.py`, port 8000) — bakes the goal definition into the workflow input at start
- **appium-mcp@1.56.3** *(PINNED — newer versions break tool names)* — persistent SSE on port 3100
- **`@playwright/mcp@latest`** for web testing (future)
- **React** chat UI on `localhost:5173`

## Project layout

```text
prompts/persona/         # Shared SOUL + identity (single source for all goals)
goals/
  __init__.py            # Casino-only goal_list. Multi-goal mode is reserved for ≥3 capabilities.
  login/                 # goal_login (LOCKED 2026-04-29)
  slingo_qa_android/     # legacy combined goal — to be split into goal_play_game + goal_session_report
tools/slingo_qa/         # Native Python tools: SmartTap, FindElementWithFallback, DetectScreen,
                         # LookupCoords, VerifyTap, SaveEvidence, GenerateReport, TapCoordinate, WaitSeconds
shared/screen_map_db.py  # SQLite: device_profiles, screen_elements (coords), screen_signatures, run_observations
data/screen_map.db       # Runtime learned DB (signatures seeded for login flow on 2026-04-29)
screen_maps/             # Static JSON seed data (legacy; runtime learning lives in data/)
activities/              # Temporal activities — agent_toolPlanner (LLM dispatch), dynamic_tool_activity (MCP + native)
workflows/               # AgentGoalWorkflow + helpers
prompt_engine/           # System-prompt assembly. Trimmed for craftsmanship 2026-05-04 — no JSON-shouting, no upstream pattern matches.
api/                     # FastAPI: /start-workflow, /send-prompt, /confirm, /end-chat, /get-conversation-history
frontend/                # React chat UI (port 5173)
scripts/
  run_worker_android.py     # Worker process (Temporal task queue: casino-qa-android)
  smoke_login.py            # Smoke: starts workflow, sends 'login', waits for `LOGIN PASS`
  seed_login_signatures.py  # Seeds verified screen signatures into screen_map.db
.claude/skills/
  mobile-goal-dev/        # Skill: recipe for adding a new platform-agnostic capability goal
  run-agent/              # Skill: bring up the full stack (docker + worker + appium-mcp)
reports/                  # Session reports, markdown, one per run
evidence/                 # Saved screenshots tagged by run/label
```

## Run / build commands

```bash
# 1. Infrastructure
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend -d

# 2. Persistent appium-mcp SSE (PINNED to 1.56.3)
ANDROID_HOME=$ANDROID_HOME npx -y appium-mcp@1.56.3 --httpStream --port=3100

# 3. Android worker (Temporal task queue: casino-qa-android)
PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py

# 4. Trigger a goal:
curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=login'

# 5. Smoke-test the locked login:
uv run scripts/smoke_login.py --timeout 300
```

After editing prompts or registering a new goal, **rebuild the API**:
```bash
docker compose -f docker-compose.yml build api && docker compose -f docker-compose.yml up -d api
```
After editing tool code (`tools/`, `activities/`, `workflows/`), **restart the worker**.

The Temporal UI for live workflow inspection: `http://localhost:8080`.

## Architectural decisions worth honouring

### Tool-use forcing for structured output (2026-05-04)
`agent_toolPlanner` uses Anthropic **tool-use forcing** on a synthetic `plan_next_action` tool whose schema is `{next, tool, args, response}`. The model's output shape is structurally guaranteed by the API. **Do not regress to prompt-prayer JSON** — that's the upstream's `parse-and-pray` pattern, which we hit JSON-decode failures on. The `tool` field is constrained per-call to an enum of the goal's actual tool names so the model literally cannot hallucinate a tool name.

### Screen-map first, LLM as fallback (canonical flow)
For every action:
```
new screen → compute (app_pkg, build_env, resolution, screen_signature)
           → look up touch-intent in screen-map
           → if hit + high confidence: deterministic tap
           → if miss: LLM/visual reasoning, then write the result back to the map
```
This makes runs cheap, fast, replayable. LLM cost should scale only with novelty. The agent gets faster every run.

### Self-healing is non-negotiable
The agent **must never get stuck**. On any tool error: try alternative selector strategies, dump page-source, fall back to coordinate tap, save evidence, continue optimistically. The only sanctioned `next='question'` is `ASK-USER-OTP` in cert/prod where SMS is real. Routine selector misses recover via `FindElementWithFallback`, not by asking the user.

### appium-mcp param names (CRITICAL — easy to get wrong)

| Tool | Required arg | Common mistake |
|------|------|----------------|
| `appium_click` | **`elementUUID`** | NOT `elementId` (that's just a label in the result text) |
| `appium_set_value` | `elementUUID`, **`text`** | NOT `value` |
| `appium_find_element` | `strategy` AND `selector` | both required |
| `appium_mobile_press_key` | `key` (BACK/HOME/etc.) | NOT digits — use `appium_set_value` to type |

Numeric-string args (OTP `"864408"`, postcodes, codes) are preserved as strings by `_STRING_ONLY_KEYS` in `activities/tool_activities.py`. **Do not remove that guard** or OTP entry breaks (model emits string, dispatcher used to coerce to int, MCP rejected as type-mismatched).

### The screen-map DB is the agent's long-term memory
Every successful tap updates confidence and selectors. Every failed tap is recorded in `run_observations`. The `screen_signatures` table is seeded from real device runs (`scripts/seed_login_signatures.py`). Treat the DB as the source of truth — code doesn't hard-code coordinates.

### The verified login flow

```
launch app → location modal Continue → system permission "While using the app"
→ FanCash reward modal Continue → notification system permission Allow
→ Fanatics ONE email screen → enter email → Continue
→ password screen → enter password → Log in
→ OTP screen → auto-fill {{DEFAULT_OTP}} (BUILD_ENV=test policy)
→ Done → Hollywood Casino home with balance + FanCash visible
→ LOGIN PASS
```

Verified 2026-04-29 on Pixel 9 Pro emulator (1344x2992, `com.betfanatics.casino.test`). Smoke: `uv run scripts/smoke_login.py`.

## Authoring a new goal

Use the `mobile-goal-dev` skill (`.claude/skills/mobile-goal-dev/SKILL.md`) — it walks you through the recipe. The TL;DR:

1. `mkdir goals/<goal_id>/prompts && cd goals/<goal_id>`
2. Write `prompts/user.md` with phase logic. Reference verified selectors only — no guessing.
3. Copy `goals/login/prompt_loader.py` and adjust.
4. Copy `goals/login/__init__.py`, set the goal id and tools.
5. Register in `goals/__init__.py` (single line).
6. Rebuild the API + restart the worker.
7. Smoke-run end-to-end before declaring it done.

Goals are **platform-agnostic**. If your goal needs Android-only behavior, that lives in the screen-map and tools, not in the goal name.

## Self-healing rules (from SOUL.md, summarised)

1. Tool error → try alternative selector strategy → if all miss, dump page-source and read it.
2. Coordinate tap (`TapCoordinate(x, y)` from page-source bounds) is the last-resort fallback.
3. Never `next='question'` for routine recovery. Only ask under `ASK-USER-OTP`.
4. ≥3 attempts on the same intent without progress → `SaveEvidence(...)` and continue.
5. Every successful recovery updates the screen-map.

## Risk tiers (from SOUL.md)

| Tier | Examples | Graduate when | Why |
|------|----------|--------------|-----|
| HIGH-RISK | `spin_button`, `stake`, `sign_in_button`, `otp_submit`, `place_bet`, `deposit_confirm` | NEVER — always verify | Wrong tap = money or auth failure |
| MEDIUM-RISK | `close`, `no_thanks_exit`, `keep_playing`, `first_result`, `continue_button` | 90% confidence + 5 uses | Test failure but no money |
| LOW-RISK | `search_bar`, grid cells, navigation tabs | 80% confidence + 3 uses | Minor retry |

After graduation, occasional spot-checks (every ~5th use) keep the map honest. A single failure on a graduated element resets confidence.

## Testing

```bash
uv sync
uv run pytest                                       # full suite
uv run pytest --workflow-environment=time-skipping  # faster
uv run scripts/smoke_login.py --timeout 300         # end-to-end smoke
```

## Code style

- Python 3.10 conventions, `black`, `isort`, `mypy --check-untyped-defs --namespace-packages`.
- `uv run poe format` / `uv run poe lint` / `uv run poe test`.
- Edit existing files; don't create new top-level docs unless asked.
- Default to writing no comments. Only document the WHY when it's non-obvious.

## Commit / PR conventions

- Reference file:line when relevant (`workflows/agent_goal_workflow.py:128`).
- Describe **what** changed and **why**.
- Tests must pass before merge: `uv run pytest --workflow-environment=time-skipping`.
- Don't push to remote unless the user asks.

## Where things live elsewhere

| Doc | Purpose |
|---|---|
| [SOUL.md](../casino-game-player/SOUL.MD) | The agent's identity. **Read this first.** Mirrored into `prompts/persona/soul.md` for runtime injection. |
| [Constitution](.specify/memory/constitution.md) | Casino QA architecture decisions and target matrix |
| [`.claude/skills/mobile-goal-dev/SKILL.md`](.claude/skills/mobile-goal-dev/SKILL.md) | Recipe for adding a new capability goal |
| Project memory (`~/.claude/...../memory/`) | Cross-session feedback rules — load-bearing context for any future agent |
