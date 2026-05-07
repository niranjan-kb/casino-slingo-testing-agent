# Quickstart — Casino Game-Play & Verification Suite

**Branch**: `005-casino-game-play-suite` · **Date**: 2026-05-06

How to put the agent on the casino floor and let it play. Three processes (already familiar from the auth POC), one new env var, six smoke commands, four verification rituals.

## 0. Prerequisites

- macOS host with Android Studio + KVM (`PT-2`).
- Python 3.10 in `.venv` via `uv` (existing).
- AWS Bedrock SSO valid: `aws sso login --profile bedrock`.
- `.env` includes the **stop-loss**:

```bash
# .env
LLM_MODEL=bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
APPIUM_MCP_SSE_URL=http://localhost:3100/sse
ANDROID_HOME=/Users/<you>/Library/Android/sdk
PLATFORM=android
BUILD_ENV=cert
MAX_LOSS_USD=10                       # the night's bankroll cap. Hard ceiling.
SCREEN_MAP_STALENESS_DAYS=30          # global default; per-surface overrides set on promotion
OUTCOME_DRIFT_THRESHOLD=0.30          # below this is noise; above is a regression
PROPOSALS_PER_WEEK_BUDGET=50          # pit-boss queue cap; over → exploration auto-throttles
SHOW_CONFIRM=False                    # autonomous smoke runs in cert
```

## 1. Boot the casino (three processes, in order)

```bash
# 1. Infrastructure (no override file — avoids API --reload that resets the goal)
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend -d

# 2. Persistent appium-mcp (PINNED to 1.56.3)
ANDROID_HOME=$ANDROID_HOME npx -y appium-mcp@1.56.3 --httpStream --port=3100

# 3. Android worker — loads intent registry, plan graph, tool registry, screen_map.db
PLATFORM=android BUILD_ENV=cert ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py
```

Web UIs:
- Temporal UI (every LLM call, every tool dispatch, every signal): http://localhost:8080
- API: http://localhost:8000
- Frontend: http://localhost:5173

## 2. Send the agent to a table — the six smoke runs

Each smoke command sets up a single workflow, sends a vague prompt, waits for terminal, and writes `reports/<date>-<run>.{json,md}`. Each maps to one of US1–US6 in [spec.md](./spec.md).

```bash
# US1 — Spin to Win (slot, no bonus)
uv run scripts/smoke_play_intent.py --game spin_to_win --prompt "play fanatics spin to win" --timeout 600

# US2 — Blackjack (single hand, dealer-state polling)
uv run scripts/smoke_play_intent.py --game blackjack --prompt "play fanatics blackjack" --timeout 900

# US3 — Fire Roulette (time-pressured betting window)
uv run scripts/smoke_play_intent.py --game fire_roulette --prompt "play fanatics fire roulette" --timeout 900

# US4 — Multihand Blackjack (parallel decision streams)
uv run scripts/smoke_play_intent.py --game multihand_blackjack --prompt "play fanatics multihand blackjack" --timeout 900

# US5 — Slingo (5x5 grid + bonus sub-flow)
uv run scripts/smoke_play_intent.py --game slingo_classic --prompt "play slingo" --timeout 1200

# US6 — A slot (any production slot the resolver picks)
uv run scripts/smoke_play_intent.py --game any_slot --prompt "play any slot for 5 minutes" --timeout 600
```

The first time the agent visits a new table, it's slower — it's *learning the rules of the house* (filling in `game_playbook` rows, observing animation timings, proposing novel screens). Subsequent runs on the same build are fast because the path planner walks the screen-graph deterministically.

## 3. Watch the agent play

While a smoke is running:
- **Live transcript**: `tail -f reports/<run_id>.log`
- **Temporal UI**: open the workflow at http://localhost:8080 — every LLM call is a workflow event with input/output.
- **Mid-run cost**: `uv run scripts/cost_meter.py --workflow <id>` prints rolling per-turn input-token p50 and prompt-cache hit rate.

## 4. After the night ends — review the take

```bash
# Open the latest run report
open reports/$(ls -t reports/ | head -1)

# Or the structured form for tooling
cat reports/$(ls -t reports/*.json | head -1) | jq '.balance, .terminal_reason, .operator_actions'
```

Report sections worth reading first:
- `balance.delta` — did the agent win or lose? Was it within stop-loss?
- `terminal_reason` — what ended the visit? (`budget_exhausted` / `n_spins` / `max_minutes` / `panic` / ...)
- `operator_actions[]` — the pit boss's homework: pending proposals, demoted graduated rows, throttled exploration, degraded optimizations.
- `optimizations.*` — every optimization should read `active`. Any `degraded` is a regression.

## 5. The pit boss's daily ritual (US9)

Every morning, the human reviews what the agent stumbled into yesterday and accepts or rejects.

```bash
# Scan novel rooms the agent saw last night, deduped by structural skeleton
uv run scripts/scan_signature_proposals.py --since 24h
# ... renders a clustered list. e.g. 12 raw hashes → 3 clusters: lobby_promo_banner, geo_warning_modal, slingo_bonus_intro

# Accept a cluster, name the canonical screen
uv run scripts/accept_signature_proposal.py <cluster_id> --as slingo_bonus_intro
# ... binds all hashes in the cluster to logical_id 'slingo_bonus_intro'.
# Next run: the screen graph resolves it deterministically — no proposal regenerated.

# Reject as noise (banner rotation, A/B variant)
uv run scripts/accept_signature_proposal.py <cluster_id> --reject --cooldown 30d
```

Queue saturation: if pending proposals exceed `PROPOSALS_PER_WEEK_BUDGET`, exploration self-throttles (lower exploration ratio) and the run report flags it under `operator_actions[kind=exploration_throttled]`.

## 6. Verify the self-improving loop (US7)

Run goal X twice on a stable build, with pit-boss review in between. The second run should cost materially less.

```bash
# First run — agent encounters novel screens
uv run scripts/smoke_play_intent.py --game slingo_classic --prompt "play slingo" --timeout 1200
# Note: total LLM turns from report.intents[].llm_calls

# Pit-boss reviews proposals
uv run scripts/scan_signature_proposals.py --since 1h
# ... accept the real screens, reject the noise

# Second run — same goal, same build
uv run scripts/smoke_play_intent.py --game slingo_classic --prompt "play slingo" --timeout 1200
# Compare: report.intents[].llm_calls should be ≥40% lower (SC-004)

# Side-by-side
uv run scripts/run_compare.py <first_run_id> <second_run_id>
```

## 7. Verify the casino floor map is growing (US8)

```bash
# Send the agent on a scouting trip with a fixed budget
uv run scripts/smoke_explore.py --max-screens 30 --max-minutes 20

# Draw the map of what it's seen
uv run scripts/render_graph.py --build cert --out graph.html
open graph.html
# ... interactive map: click a room → screenshot evidence; click a door → list of nights it was walked through.

# What changed since last main-branch baseline?
uv run scripts/graph_diff.py --baseline graphs/baselines/main.snapshot --against current --out diff.md
cat diff.md
# ... added rooms, removed rooms, distribution-shifted doors (A/B variants ≥30% drift)
```

Destructive doors (deposit, withdrawal, KYC submit, account close) are recorded but never traversed by the explorer. They are blacklisted by `screen_action_frontier.side_effect='destructive'`.

## 8. Verify the agent is not getting fat (US10)

The optimization-status panel is part of every run report. Check it explicitly on representative runs:

```bash
# All five optimizations must be "active"
jq '.optimizations' reports/<run_id>.json
# {
#   "page_source_excluded": "active",      # FR-031: no XML in planner prompts
#   "tool_result_tiering":  "active",      # FR-032: T0/T1/T2/T3 retention
#   "history_compactor":    "active",      # last-N verbatim, older summarized
#   "prompt_cache":  { "status": "active", "hit_rate": 0.92 },   # ≥0.85 (SC-007)
#   "replay_determinism":   "active"       # FR-035: replay reads from history
# }

# Per-turn input volume
jq '.intents[] | {intent_id, input_chars_p50, input_chars_p95}' reports/<run_id>.json
# input_chars_p50 ≤ 30000, p95 ≤ 45000 (SC-007)
```

Failures here are silent and expensive. The CI gate (Phase E) runs this jq pipeline on every PR-triggered smoke run; any `degraded` blocks merge.

## 9. Adding a new game — the no-code playbook

Adding a game is *data*. The agent learns the rest by playing.

```bash
# 1. The game is on the marquee — let the agent discover it
uv run scripts/smoke_play_intent.py --prompt "play <new game name>" --timeout 1200
# ... lobby-walk inserts the directory row automatically when the agent sees the tile.
#     If the resolver can't find it in directory yet, the search-bar branch types the literal query.

# 2. (Optional) Pre-seed for marquee titles ops wants the resolver to know about immediately
uv run scripts/seed_directory.py --slug new_game --kind slingo --aliases '["new game","ng"]' --popularity 5

# 3. After the first successful play, the playbook row is auto-populated from observed taps and balance reads.

# 4. (Optional, once-only) Hand-author the per-kind file IF this is a new game family
echo "name: my_new_kind\nturn_structure: [...]" > game_kinds/my_new_kind.md
# Restart the worker so the kind file loads.
```

There is no per-game Python. There is no per-game JSON. There are no per-game selectors anywhere in the repo. The agent **is** the player; the database **is** its memory.

## 10. When things go wrong — incident playbook

| Symptom | What to do |
|---|---|
| Agent stuck on same screen | Workflow auto-detects (`5 visits in 20 actions` → BackOff). If it terminates, check `reports/<id>.operator_actions` — likely a wrongly-promoted graduated row; the offender is flagged with `kind=demoted_rows`. |
| Balance read fails repeatedly | `balance_read_attempts` in round records exceeds 3 → halt with `terminal_reason=balance_unparseable`. Likely the wallet UI changed; clear the playbook's `balance_regex`, replay the run, agent re-derives. |
| Same novel modal appears every run | Pit boss didn't accept the proposal. Run `scan_signature_proposals.py` and decide. |
| Exploration silently doing nothing | Queue cap hit (`PROPOSALS_PER_WEEK_BUDGET`). Either drain the queue or raise the cap. |
| Per-turn input tokens spike | One of the optimizations went `degraded`. Check `optimizations.*` in the latest report. Common causes: page-source leaked back into prompts (regression in `_normalize_result`); cache key changed (deploy without restart). |
| Workflow non-deterministic on replay | Forbidden by FR-035. Run `tests/integration/test_replay_determinism.py`. The planner's LLM call is the only allowed non-deterministic boundary; nothing else may call out. |

## 11. The single rule

The agent never gets stuck. Selector miss → next strategy → page-source dump → coordinate fallback. ≥3 strategy failures on one intent: save evidence, continue. ≥5 failures on one screen: save evidence, stop. Never `next='question'` for routine recovery — only OTP under `ASK-USER-OTP` policy. Constitution IV is non-negotiable; everything else in this quickstart serves that rule.
