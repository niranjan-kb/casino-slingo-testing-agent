# Casino QA Agent (Danny Ocean) — Engineering Guide

Last updated: 2026-05-20

> **Single source of truth** for AI coding assistants (Claude Code, Codex, Cursor, etc.) and humans. The runtime agent is named **Danny Ocean**: *"Winning isn't the end. It's just the buy-in for the next hand."* The runtime persona lives in [`prompts/persona/soul.md`](prompts/persona/soul.md). The runtime topology diagram lives in [agent-harness.md](agent-harness.md).

> **Self-healing is non-negotiable.** The agent must never get stuck.

## Use the temporal CLI to debug the agent! 

## tl;dr for an AI editor

- **Danny Ocean** — a **casino game player** built on Temporal for visibility + durability. Player-first, QA-aware.
- **One agent, intents at runtime.** A single `AgentGoalWorkflow` picks an `active_intent` per turn from a closed-set registry of 6 — `intent_parse_session`, `intent_authenticate`, `intent_navigate_to_screen`, `intent_navigate_to_game`, `intent_play_game`, `intent_report`. New flows = new intent files. New games = `game_directory` + auto-populated `game_playbook` rows (per-game data, NOT code) — auto-seeded by the workflow after `intent_navigate_to_game` completes. New game *family* = a `game_kinds/<kind>.md` file. No goal-per-task code. Bonus rounds (slingo / live-show) ride an inline frozen-wager branch within `intent_play_game`.
- **Map primary, LLM fallback.** Every action: lookup `(app_pkg, build_env, resolution, screen_sig) → intent` in `data/screen_map.db`; deterministic tap; verify; only fall back to LLM/visual on miss. Every successful step writes back.
- Output is **structurally enforced** via Anthropic tool-use forcing on the synthetic `plan_next_action` tool. Do NOT regress to prompt-prayer JSON.
- **Self-healing is non-negotiable.** Never set `next='question'` for routine recovery — try alternative selector strategies first; ASK-USER-OTP only in cert/prod.

## Mental model — one persona, six intents

The persona (SOUL) is shared. The agent composes **intents** at runtime — the LLM picks the active intent each turn from a closed-set enum.

| Intent id | What it does | Status |
|---|---|---|
| **`intent_parse_session`** | Compile vague prompt → `SessionIntent` envelope (flow / target / budget / terminal). One-shot at session start. FR-003 hard ceiling enforced. | ✅ spec 005, first-live 2026-05-14 (T052 v9) |
| **`intent_authenticate`** | Launch app → dismiss modals → Fanatics ONE 2-step login → OTP → confirm logged-in home/lobby | ✅ Locked 2026-04-29; verified live through T052 |
| **`intent_navigate_to_screen`** | Generic from-any-screen → target signature. Used for non-play targets (settings/account/support). Tightened in 006. | ✅ spec 004 / refined spec 006 |
| **`intent_navigate_to_game`** | Lobby walk to a target game's `loaded_signature`: ordered fallback recents → category → search → scroll. On success the workflow auto-seeds `game_directory` + `game_playbook` and loads the L4 game-knowledge envelope. | ✅ spec 005 / hardened spec 006 |
| **`intent_play_game`** | Generic round-loop driver: ReadBalance → CheckBudget → action → WaitForSignature → record_round. Per-game data lives in `game_playbook` (auto-populated). First-launch bootstrap uses kind-file HIGH-risk element names. Bonus rounds handled by an inline frozen-wager branch. | ✅ spec 004 / refined spec 005-006 |
| **`intent_report`** | Write `reports/YYYY-MM-DD-<run>.{md,json}` (timeline, rounds, optimisations panel, operator-action queue). Session terminator. ⚠️ Known issue: LLM skips `GenerateReport` call — workflow-side enforcement pending. | ✅ spec 004 |

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
Every successful `TapMapped` / `VerifyTap` writes to `screen_transitions` via `record_transition_observation`. Every `FindElement` hit (with caller-supplied coords) writes to `screen_elements`. All wrapped in try/except — observer-side or auto-recorder failures must NEVER halt the goal loop (FR-027).

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

- **New intent (rare):** drop a markdown file in `intents/` (≤600 tokens; frontmatter `id`, `end_state_signatures`, `success_check`, `guardrails`, `risk_tier`). Restart the worker — the registry loads at module import; no Python edit. If the new intent should be plan-graph-gated, add a node to `graphs/casino_session.yaml`.
- **New game (common):** the `game_directory` row is auto-discovered by lobby-walk (`observers/screen_identity.extract_game_tiles_from_lobby`). For marquee titles ops can pre-seed via `scripts/seed_directory.py` (T104). The `game_playbook` row is auto-populated on first launch — no per-game JSON, no per-game Python.
- **New game family (rare):** add `game_kinds/<kind>.md` (≤400-tokens target). The L4 prompt layer caches them at module import; restart the worker.
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
| [specs/005-casino-game-play-suite/](specs/005-casino-game-play-suite/) | Game-play suite spec — parse_session / navigate_to_game / play_game / report refinement |
| [specs/006-app-navigation/](specs/006-app-navigation/) | **In flight** — registry slimming (8→6 intents), post-navigate auto-seed, L4 wiring, reliable game-find, `app_structure.md` prompt layer |
| [fancash_spins.md](fancash_spins.md) | Reference doc on the FanCash Spins / "spin to win" daily-bonus feature (bottom-nav entry, not a regular game tile) |
| [games.md](games.md) | Top-100 games catalogue + state availability (MI/PA/NJ/WV); informs `game_directory` and kind taxonomy |
| Project memory (`~/.claude/.../memory/`) | Cross-session feedback rules |

## Active Technologies
- Python 3.10 (existing `.venv` via `uv`) + `temporalio` (durable workflow spine), `litellm` → AWS Bedrock (`claude-sonnet-4-5`), `pyyaml`, MCP via SSE (`appium-mcp@1.56.3` PINNED per MCP-2), `appium-mcp` over `httpx` for SSE (004-nav-graph-intents)
- SQLite (`data/screen_map.db`) as runtime source of truth (Principle I); Temporal workflow history for conversation + tool results; markdown files in `intents/` and `prompts/persona/` for declarative conten (004-nav-graph-intents)
- Python 3.10 (`.venv` via `uv`). + `temporalio` (durable spine, replay-deterministic), `litellm` → AWS Bedrock (`claude-sonnet-4-5` via `bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0`), `pyyaml` (intents, manifests, plan graph), `httpx` (MCP SSE). MCP layer: `appium-mcp@1.56.3` (PINNED per MCP-2) on port 3100, persistent SSE. (005-casino-game-play-suite)
- SQLite at `data/screen_map.db` is the runtime source of truth (Principle I). Tables added below in §"Project Structure → Data". Markdown files in `intents/` and `game_kinds/` are declarative spec only (≤600 / ≤400 tokens). No JSON seed files for game playbooks (the playbook auto-populates). (005-casino-game-play-suite)

## Recent Changes
- **2026-05-20 — spec 006 Sprint A (registry slim + auto-seed + L4 wiring)**: closed-set registry trimmed 8→6 intents (`intent_play_bonus` deleted — bonus rounds now an inline frozen-wager branch inside `intent_play_game`; `intent_load_game_context` deleted — replaced by a workflow-side post-navigate auto-seed). Three new Temporal activities (`upsert_game_directory_activity` / `upsert_game_playbook_activity` / `load_game_context_activity` in `activities/intent_activity.py`) + `upsert_game_playbook` / `get_game_context` methods in `shared/screen_map_db.py`. Workflow gained `self.game_context` and threads it into `generate_genai_prompt(game_context=...)` for the L4 layer. ReadBalance retry budget enforced workflow-side: 3 consecutive `found=False` results emits a strong directive prompt nudging CheckBudget to terminal=balance_unparseable. Contract test asserts registry==6. `goals/casino_session/prompts/user.md` rewritten as the 6-intent + screen-driven-recovery overview.
- **006-app-navigation Phase A + Path A**: new `prompts/persona/app_structure.md` layer (cacheable, ≤800 tokens), `intent_navigate_to_game.md` hardening (no short-circuit on `ResolveDirectory unresolved`; ≥1 verified tap before `next=done`), `intent_navigate_to_screen.md` recovery anchors, lobby-walk auto-discovery patches (`_LOBBY_SCREEN_IDS` += `home`; `_TILE_ID_SUBSTRINGS` += Fanatics' real tile rids), `extract_game_tiles` slug-collision fix, `any_terminal` reachability predicate fix, recovery_reentry tracking. See [specs/006-app-navigation/](specs/006-app-navigation/).
- **2026-05-14 — T052 v9 live evidence**: full 4-intent chain (`parse_session → authenticate → navigate_to_game → report`) ran end-to-end on the test build (run id `86fc0d35-b3c7-4ac6-b8dc-226d46185151`) with zero crashes. Auth + parse_session now considered stable. Game-find gap is the new gating step. Five latent workflow bugs caught + fixed during the v5→v8 cycle (summarizer dispatch, format_history compaction, CombinedInput dataclass, summary string-coerce, CAN carry-prompt) — long-context post-auth workflow path now exercised.
- **2026-05-14 — prompt-stack hardening**: 8 C/H audit items fixed in one pass — `goal_casino_session/prompts/user.md` rewritten from auth-only to session-scope; `agent_friendly_description` updated to list the intents (superseded by 6-intent rewrite in spec 006 Sprint A); starter prompt now invites free-text session asks; `appium_scroll` added to whitelist; `system_back` references replaced with `appium_mobile_press_key key="BACK"`; `intent_play_game` first-launch bootstrap clarified; `tools.md` extended to cover all 13 local tools; 8 tool-registry YAMLs cleaned of dangling `intent_explore` references.
- **Game-kind restructure**: 8 kinds now in `game_kinds/` — `slingo`, `slots` (with provider-variants section), `blackjack` (RNG), `roulette` (RNG), `live_blackjack`, `live_roulette`, `baccarat`, `live_show`. Each documents the EVONET-unavailable-in-WV jurisdiction guard. `spin-to-win.md` moved to repo-root `fancash_spins.md` (Daily Spin is a bottom-nav daily-bonus feature, not a game-kind).
- **005-casino-game-play-suite (in flight)**: directory/playbook split for game data (`game_directory` pre-launch + `game_playbook` post-launch, auto-populated — replaces `game_catalog`); plan-graph guard on intent transitions (`graphs/casino_session.yaml`, loaded module-level per worker); 5 new tools — `ParseSessionIntent` / `ResolveDirectory` / `ReadBalance` / `CheckBudget` / `WaitForSignature` (Welford-online learned-wait, animation_timings keyed on build_env+app_version per FR-021); planner-prompt overhaul T024–T027 (page-source XML stripped from history, intent-conditional tool filter via `tools/registry/*.yaml`, L4 game-knowledge layer, last-N=2 verbatim + summarised history). Live measured: −39% wall-clock at constant LLM-call count.
- **Repo-rename**: `tools/slingo_qa/` → `tools/casino_qa/` (now hosts all casino-game tools, not just Slingo). Legacy `goals/slingo_qa_android/` is slated for removal in T109 (after US1 ships green).
- 004-nav-graph-intents: Added Python 3.10 (existing `.venv` via `uv`) + `temporalio` (durable workflow spine), `litellm` → AWS Bedrock (`claude-sonnet-4-5`), `pyyaml`, MCP via SSE (`appium-mcp@1.56.3` PINNED per MCP-2), `appium-mcp` over `httpx` for SSE
