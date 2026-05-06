# Casino QA Agent — Engineering Guide

Last updated: 2026-05-06

> **Single source of truth** for AI coding assistants (Claude Code, Codex, Cursor, etc.) and humans. The runtime persona lives in [`prompts/persona/soul.md`](prompts/persona/soul.md). The runtime topology diagram lives in [agent-harness.md](agent-harness.md).

## tl;dr for an AI editor

- A **casino game player** built on Temporal for visibility + durability. Player-first, QA-aware.
- **One agent, intents at runtime.** A single `AgentGoalWorkflow` picks an `active_intent` per turn from a closed-set registry of 4 (`intent_authenticate`, `intent_navigate_to_screen`, `intent_play_game`, `intent_report`). New flows = new intent files. New games = `game_catalog` rows. No goal-per-task code.
- **Map primary, LLM fallback.** Every action: lookup `(app_pkg, build_env, resolution, screen_sig) → intent` in `data/screen_map.db`; deterministic tap; verify; only fall back to LLM/visual on miss. Every successful step writes back.
- Output is **structurally enforced** via Anthropic tool-use forcing on the synthetic `plan_next_action` tool. Do NOT regress to prompt-prayer JSON.
- **Self-healing is non-negotiable.** Never set `next='question'` for routine recovery — try alternative selector strategies first; ASK-USER-OTP only in cert/prod.

## Mental model — one persona, four intents

The persona (SOUL) is shared. The agent composes **intents** at runtime — the LLM picks the active intent each turn from a closed-set enum.

| Intent id | What it does | Status |
|---|---|---|
| **`intent_authenticate`** | Launch app → dismiss modals → Fanatics ONE 2-step login → OTP → confirm logged-in home/lobby | ✅ Locked 2026-04-29 |
| **`intent_navigate_to_screen`** | From any logged-in screen, reach a target screen (typically a game's loaded signature) via search / category / recents | 🆕 spec 004 |
| **`intent_play_game`** | Generic spin-loop driver. Per-game data lives in `game_catalog.play_loop_json` — no per-game code | 🆕 spec 004 |
| **`intent_report`** | Write `reports/YYYY-MM-DD-<run>.md` (timeline, observations, transitions added). Session terminator. | 🆕 spec 004 |

A goal (`goal_casino_session`) is the workflow's session config — tool list + MCP server + starter prompt. An intent is the LLM's per-turn objective (declarative end-state, success check, guardrails). One goal per workflow; many intents over its lifetime. See [agent-harness.md](agent-harness.md) for the full diagram.

## Why Temporal

- **Visibility** — every LLM call, tool dispatch, signal is a workflow event in the Temporal UI at `localhost:8080`.
- **Durability** — worker crash mid-spin replays to the exact step. Activities have `RetryPolicy`.
- **Audit trail** — conversation history is a workflow query; no separate DB needed.

## Stack

- **Python 3.10** via `uv` (`.venv`)
- **Temporal SDK** (durable spine), **LiteLLM** → Bedrock (`claude-sonnet-4-5`)
- **FastAPI** (8000), **React** UI (5173), **Temporal UI** (8080)
- **appium-mcp@1.56.3** *(PINNED — newer versions break tool names)*, persistent SSE on 3100

## Run

```bash
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend -d
ANDROID_HOME=$ANDROID_HOME npx -y appium-mcp@1.56.3 --httpStream --port=3100
PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py

curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=login'

uv run scripts/smoke_login.py --timeout 420            # auth-only
uv run scripts/smoke_play_intent.py --timeout 600      # full intent sequence (spec 004)
```

After editing **prompts or goals**: rebuild the API (`docker compose ... build api && up -d api`) — it bakes the goal definition into the image at build time. After editing **tools / activities / workflows**: restart the worker.

## Architectural decisions worth honouring

### Tool-use forcing for structured output
`agent_toolPlanner` calls Anthropic with `tool_choice` forcing on a synthetic `plan_next_action` tool. The schema enforces `next / tool / args / response / active_intent` shape. The `tool` and `active_intent` fields are constrained per-call to enums of the goal's tool names and the loaded intent registry — the model literally cannot hallucinate either. **Do NOT regress to JSON parsing.**

### Map-first action flow (canonical)

```
new screen → compute (app_pkg, build_env, resolution, screen_signature)
           → look up touch-intent in screen_map.db
           → if hit + high confidence: deterministic tap
           → if miss: LLM/visual reasoning, then write the result back
```

LLM cost scales only with novelty. Third+ runs of any flow are ~zero-LLM. **Read-time decay** in `shared/screen_graph._effective_confidence`: build-mismatch ×0.5, linear staleness ramp past 30 days (env: `SCREEN_MAP_STALENESS_DAYS`). Stored confidence is never destructively modified.

### Auto-record (spec 004 / MW-1, MW-2)
Every successful `SmartTap` / `VerifyTap` writes to `screen_transitions` via `record_transition_observation`. Every `FindElementWithFallback` hit (with caller-supplied coords) writes to `screen_elements`. All wrapped in try/except — observer-side or auto-recorder failures must NEVER halt the goal loop (FR-027).

### Self-healing
Selector miss → next strategy → page-source dump → coordinate fallback. ≥3 failed strategies on one intent: `SaveEvidence`, continue. ≥5 failures on one screen: `SaveEvidence`, STOP. The only sanctioned `next='question'` is OTP under `ASK-USER-OTP` policy.

### appium-mcp param names (CRITICAL — easy to get wrong)

| Tool | Required arg | Common mistake |
|---|---|---|
| `appium_click` | **`elementUUID`** | NOT `elementId` |
| `appium_set_value` | `elementUUID`, **`text`** | NOT `value` |
| `appium_find_element` | `strategy` AND `selector` | both required |
| `appium_mobile_press_key` | `key` (BACK/HOME/…) | NOT digits — use `appium_set_value` to type |

Numeric strings (OTP `"864408"`, postcodes) are preserved by `_STRING_ONLY_KEYS` in `activities/tool_activities.py`. Do NOT remove that guard.

### Risk tiers (gates `should_verify_tap` graduation)

| Tier | Examples | Graduate when |
|---|---|---|
| HIGH | spin_button, place_bet, otp_submit, sign_in_button | NEVER — always verify |
| MEDIUM | close_button, keep_playing, first_result | 90% confidence + 5 uses |
| LOW | search_bar, grid cells, nav tabs | 80% confidence + 3 uses |

A single failure on a graduated row resets confidence.

## Adding a new intent / new game

- **New intent (rare):** drop a markdown file in `intents/` (≤600 tokens; frontmatter `id`, `end_state_signatures`, `success_check`, `guardrails`, `risk_tier`). Restart the worker — the registry loads at module import; no Python edit.
- **New game (common):** add a `game_catalog` row with `slug`, `name`, `category`, `loaded_signature`, optional `play_loop_json`. The agent discovers it via `intent_navigate_to_screen` → `intent_play_game`.
- **Unknown screens** seen ≥3× across ≥2 runs are surfaced via `scripts/scan_signature_proposals.py`. Promote with `scripts/accept_signature_proposal.py <hash> --as <name>`. Auto-promotion forbidden (FR-022).

## Testing

```bash
uv sync
uv run pytest --workflow-environment=time-skipping
uv run scripts/smoke_login.py --timeout 420
uv run scripts/smoke_play_intent.py --timeout 600
```

## Code style

- Python 3.10, `black`, `isort`, `mypy --check-untyped-defs --namespace-packages`
- `uv run poe format / lint / test`
- Default to **no comments**. Document only the WHY when non-obvious.
- Edit existing files; don't create new top-level docs unless asked.

## Commit conventions

- Reference `file:line` when relevant (`workflows/agent_goal_workflow.py:128`).
- Describe **what** changed and **why**.
- Tests must pass: `uv run pytest --workflow-environment=time-skipping`.
- Don't push to remote unless asked.

## Where things live elsewhere

| Doc | Purpose |
|---|---|
| [SOUL.md](../casino-game-player/SOUL.MD) | The agent's identity. Read first. Mirrored to `prompts/persona/soul.md`. |
| [agent-harness.md](agent-harness.md) | Runtime topology diagram (ASCII + Mermaid) |
| [.specify/memory/constitution.md](.specify/memory/constitution.md) | Architecture rules and target matrix (v3.0.0) |
| [specs/004-nav-graph-intents/](specs/004-nav-graph-intents/) | Intent layer spec, plan, contracts |
| Project memory (`~/.claude/.../memory/`) | Cross-session feedback rules |
