# Phase 0 Research — Casino Game-Play & Verification Suite

**Branch**: `005-casino-game-play-suite` · **Date**: 2026-05-06

Resolves all open design questions surfaced in `plan.md`. No `NEEDS CLARIFICATION` markers remain after this document.

---

## R1. Resolver design — query → game_directory slug

**Decision**: Pure SQLite, no LLM. Pipeline: (a) exact `slug` match, (b) `kind` filter when known + `LIKE` substring on display_name and `aliases_json`, (c) token-set-ratio fallback (Python-side, no extra dependency — small custom function), (d) rank by `popularity DESC, last_played_at DESC`. Zero hits → mark `unresolved=true` → `intent_navigate_to_game` falls through to the search-bar branch with the literal query.

**Rationale**:
- The directory is small (≤200 games). LLM-grade fuzzy matching is overkill and non-deterministic.
- Pure SQL keeps replay deterministic and cheap.
- `aliases_json` (JSON array column) handles common typos and abbreviations without ML.
- A dedicated eval set (`tests/integration/test_resolver_eval_set.py`, 50+ canonical queries with expected slugs) prevents silent regressions ("blackjack" → "black gold slots").

**Alternatives considered**:
- LLM-based matching — rejected: non-deterministic, breaks replay, costly per turn, overkill at this scale.
- Trigram extension (`sqlite-trigram`) — rejected: extra build dependency for marginal accuracy gain on a 200-row table.
- Hybrid (LLM only on K=0) — deferred: the search-bar fallback already handles K=0 by typing the query into the app's own search; the app's search is the LLM equivalent we already trust.

---

## R2. Tool registry shape and per-intent filtering

**Decision**: Each tool ships a registry side-car at `tools/registry/<ToolName>.yaml`:
```yaml
name: SmartTap
platforms: [android]                  # extensible to ios|web later
intents: [authenticate, navigate_to_game, play_game, play_bonus, explore]
risk_tier: medium                     # informs default verification policy
schema_ref: schemas/smart_tap.json
side_effects: [screen_transition, db_write]
```
At worker boot, registry is loaded into a dict. `prompts/generators.py` filters the `tool_choice.tools` enum on each planner turn by intersecting `tools.intents ∋ active_intent` and `tools.platforms ∋ RuntimeFacts.platform`.

**Rationale**:
- Filters cut the Anthropic input-token bill (FR-033 + R10) by ~40% on intent_authenticate (8 of 21 tools instead of 21).
- Side-car YAML keeps tool definitions colocated with code without bloating import time.
- Intent-list and platform-list as data prevents per-platform code forks downstream.

**Alternatives considered**:
- In-tool decorators (`@register_tool(intents=...)`) — rejected: less reviewable in PRs; YAML diff-friendly.
- One central `tools/registry.yaml` — rejected: every tool change touches the same file → merge conflicts.

---

## R3. Plan-graph guard

**Decision**: `graphs/casino_session.yaml` declares nodes (each pointing to an intent), edges (preconditions like `requires: authenticate.success`), guards (e.g. `BudgetCheck` after each play round), and recovery routes. The workflow loads the graph at boot and exposes a `is_reachable(active_intent, current_state)` method to `intent_activity.py`. The planner's emitted `active_intent` is rejected (workflow falls back to last-known reachable intent + saves evidence) if not reachable.

**Rationale**:
- Removes the four `### Phase N` prose blocks from the goal markdown (~6.4 KB of prompt bloat per turn).
- Replay-safe: graph is workflow-input, captured in history; reachability is a pure function.
- Encodes the "no hardcoding" mandate at the structural layer — flow control is a YAML diff, not a Python diff.

**Alternatives considered**:
- LLM picks freely (status quo) — rejected: prone to skipping authenticate or repeating completed phases under prompt drift.
- Workflow hardcodes the sequence in Python — rejected: violates II (intent registry should drive flow) and the no-hardcoding mandate.

---

## R4. Per-surface decay (gaps A2)

**Decision**: Add `screen_signatures.staleness_days` (nullable INTEGER). Read-time decay falls back to env `SCREEN_MAP_STALENESS_DAYS=30` when null. Defaults applied at operator promotion based on logical-name prefix:

| Surface (logical-name prefix) | Default staleness_days |
|---|---|
| `auth_*`, `kyc_*`, `settings_*` | 90 |
| `game_*` (in-game stable: spin button, paytable) | 60 |
| `lobby_home`, `lobby_category_*` | 14 |
| `promo_banner_*`, `whats_new_*`, `recommendations_*` | 7 |

Hubs (`is_hub=true`) inherit the parent's value.

**Rationale**: Login screens are stable for months; promos rotate weekly. A single global threshold is too generous on promos and too aggressive on auth.

**Alternatives considered**:
- Global `SCREEN_MAP_STALENESS_DAYS` only — rejected: can't tune both ends.
- Per-element `staleness_days` (instead of per-signature) — rejected: too granular; surfaces are the natural axis.

---

## R5. Stochastic-outcomes migration

**Decision**: Additive new table `transition_outcomes(start_sig, action, end_sig, observed_count, last_seen, PRIMARY KEY(start_sig, action, end_sig))`. Auto-recorder writes UPSERT increment `observed_count` on each verified tap. `screen_transitions` becomes a SQL view that returns the top-`observed_count` end_sig per `(start_sig, action)` for backward compatibility while callers migrate.

**Rationale**:
- A/B variants and banner rotation produce 1-to-N edges legitimately.
- Report-diff thresholds distribution shift at ≥30% relative change in count over the last 7 runs (configurable env: `OUTCOME_DRIFT_THRESHOLD=0.30`); below threshold = noise.
- View shim means existing path-planner code continues to work; gradual call-site migration possible.

**Alternatives considered**:
- Mutate `screen_transitions` schema directly — rejected: existing callers break; prefer additive.
- Drop `screen_transitions` immediately, force callers to migrate — rejected: too invasive for one feature.

---

## R6. Replay determinism — explicit boundary

**Decision**: The planner LLM call is contained in `dynamic_tool_activity` → `agent_toolPlanner` (existing). No edits required; document explicitly:
> The planner activity is the **only** non-deterministic boundary in the workflow. On replay, Temporal returns the captured tool-use response from history; the LLM is never re-invoked.

Write a contract test (`tests/integration/test_replay_determinism.py`) that:
1. Records a workflow's history.
2. Replays it with a mocked Anthropic client that raises if called.
3. Asserts the replay completes successfully — proving no LLM call occurs.

Document the rule in `agent-harness.md` so it cannot be accidentally violated by future authors.

**Rationale**: Mandate exists implicitly; making it visible (doc + test) is the cheapest enforcement.

**Alternatives considered**:
- Add a runtime guard that errors if the planner activity is invoked during replay — rejected: Temporal SDK already enforces this; adding a second guard is belt-and-suspenders.

---

## R7. DOM-skeleton dedup for proposals

**Decision**: Compute `dom_skeleton_hash` from page-source XML by stripping all text content, image references, dynamic IDs (any attribute matching `[a-f0-9]{8,}`), and timestamps; keeping only element type + structural hierarchy. Store on every proposal. Triage tool groups by skeleton; canonical = highest-signature-occurrence variant. Operator accepts the canonical with `--as <logical_name>`; all hashes in the cluster are bound to the logical via `screen_signatures.logical_id`.

**Rationale**:
- Banner rotation and A/B variants share structure but differ in text/images.
- Skeleton hashing is local Python (no model call), deterministic.
- Bounded cluster expansion: integration test `test_dedup_clustering.py` asserts 10 near-dupes → ≤3 clusters (SC-006).

**Alternatives considered**:
- Visual perceptual hashing — rejected: heavy dependency, doesn't tolerate text changes well.
- Embedding-based clustering (Anthropic embeddings) — rejected: non-deterministic, costs per run, overkill at <200 screens.

---

## R8. Animation-timing learned-wait

**Decision**: `WaitForSignature(action, fallback_signature)` activity:
1. If `animation_timings(game_slug, action, build_env, app_version).samples >= 5`: timeout = `p95 + 2σ`.
2. Else: timeout = `game_kinds/<kind>.md` declared `learned_default` for that action (e.g., spin_to_idle_ms: 4500).
3. Else: stable-UI detector — wait until 800 ms of no DOM change AND target signature reached.
4. On every successful wait, online-update the timing row (incremental mean/stddev/p95 via Welford's algorithm).

**Rationale**:
- Removes hard-coded `WaitSeconds(5)` from any future `play_loop_json` (anti-hardcoding).
- Per-(game, action, build, version) keying tolerates app version bumps.
- Online stats avoid storing every sample.

**Alternatives considered**:
- Fixed waits — rejected: anti-hardcoding mandate.
- Single global timeout — rejected: bonus animations are 10× longer than spins.

---

## R9. Bonus novelty exploration

**Decision**: `intent_play_bonus` triggers on a known `bonus_trigger_signature` from `game_playbook`. When the bonus enters a sub-screen with no signature in `screen_signatures`, the activity sets `frozen_wager=true` (no further bets), enforces `max_actions=30`, and exits when:
- Base-grid signature reappears, OR
- 30 actions exhausted (save evidence + force `system_back` until base grid), OR
- Loop detector trips (5 visits of same screen in 20 actions).

Novel screens encountered during bonus exploration land in `signature_proposals` for operator review. No further wagers are placed during exploration — the original wager already happened.

**Rationale**:
- Real-money risk during exploration is bounded by *not betting*, not by budget.
- Frozen wager + capped actions + signature-driven exit handles unknown bonus mini-games safely.

**Alternatives considered**:
- Refuse to enter unknown bonuses — rejected: the wager already triggered the bonus; refusing means leaving money on the table and never learning the screens.
- Run full LLM autonomy in bonus — rejected: unbounded turn count, unbounded cost.

---

## R10. Anthropic prompt-cache invalidation

**Decision**: No explicit invalidation API needed. The Anthropic `cache_control: ephemeral` cache has a 5-minute TTL and is keyed on prefix exactness. Cache busts naturally on:
- Worker process restart (any deploy ships new bytes → restart → fresh process → no in-memory state survives).
- `prompts/persona/soul.md` change (rebuild + restart).
- Tool registry change (new YAML → restart).
- Intent registry change (new file in `intents/` → restart).
- `appium-mcp` version change (worker restart loads new tool descriptions).

Document the rule in CLAUDE.md and `agent-harness.md`: **any deploy that ships new bytes restarts the worker, which restarts the cache cycle**. No long-lived in-memory cache may outlast the process.

**Rationale**: Process-restart is the universal invalidator. Adding an explicit `cache_version` env var would be cheap insurance but is not required by FR-033.

**Alternatives considered**:
- Per-prelude version stamp baked into `cache_control.version` — deferred: revisit if the 5-min TTL ever causes silent cross-deploy contamination.

---

## Open follow-ups (NOT blocking this plan)

These are flagged in `gaps-and-guardrails.md` and tracked there:
- Operator throughput cap (`PROPOSALS_PER_WEEK_BUDGET` env var). Default 50; auto-throttle when exceeded. Wired in Phase E.
- `transition_observations` retention (90-day rollup → summary). Wired in Phase E.
- DB write-lock during operator scripts. Wired in Phase E.

None of these block any user story (US1–US10) for this feature.
