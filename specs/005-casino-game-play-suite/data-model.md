# Data Model — Casino Game-Play & Verification Suite

**Branch**: `005-casino-game-play-suite` · **Date**: 2026-05-06

The runtime source of truth is `data/screen_map.db` — the agent's **memory of the casino floor**. Every room (screen) it has stood in, every door (transition) it has walked through, every control on every machine (element), every game on the marquee (directory), every house rule it has learned about a specific table (playbook), every bonus round timing it has clocked. Markdown files in `intents/` and `game_kinds/` are the agent's **operating manual**: what kinds of moves it can declare it's making, and what each game family looks like at a conceptual level. Nothing about a specific table is in code.

This document defines the schema additions for this feature. Existing tables (`screen_signatures`, `screen_elements`, `screen_transitions`, `signature_proposals`, `device_profiles`, `observation_log`) keep their current shape unless explicitly extended below.

---

## 1. The marquee — `game_directory`

What's playable in this casino. Populated by walking the lobby floor; ops can pre-seed marquee titles.

```sql
CREATE TABLE IF NOT EXISTS game_directory (
  slug                    TEXT PRIMARY KEY,
  display_name            TEXT NOT NULL,
  kind                    TEXT NOT NULL,                  -- slingo|slots|blackjack|roulette|...
  aliases_json            TEXT NOT NULL DEFAULT '[]',     -- ["slingo riches","slingo classic"]
  popularity              INTEGER NOT NULL DEFAULT 0,     -- ordering hint for resolver
  available               INTEGER NOT NULL DEFAULT 1,     -- 0 means delisted
  loaded_signature        TEXT,                           -- signature_hash of the loaded game screen
  first_seen_in_lobby_at  TIMESTAMP,
  last_seen_in_lobby_at   TIMESTAMP,
  last_played_at          TIMESTAMP,
  build_env               TEXT NOT NULL,                  -- test|cert|prod
  app_version             TEXT NOT NULL,
  created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_directory_kind        ON game_directory(kind);
CREATE INDEX IF NOT EXISTS ix_directory_popularity  ON game_directory(popularity DESC, last_played_at DESC);
```

**Write paths**:
- Lobby-walk activity (extension to `observer_activity.py`): on each lobby screen, parse visible game tiles → upsert directory rows. Slug from accessibility-id; display name from text label; kind from category tab the tile lives under (when known); aliases discovered over time.
- `accept_signature_proposal.py --as game_<slug>_loaded` sets `loaded_signature`.
- Played-game completion bumps `last_played_at` and `popularity`.

**Reads**: resolver in `tools/slingo_qa/ResolveDirectory.py` (R1).

---

## 2. The house rules — `game_playbook`

The agent's accumulated knowledge of *how to play* a specific table. Empty until the agent has been at the table at least once. Refines over runs.

```sql
CREATE TABLE IF NOT EXISTS game_playbook (
  slug                       TEXT PRIMARY KEY REFERENCES game_directory(slug),
  actions_json               TEXT NOT NULL DEFAULT '{}',   -- {spin: {selector_label:"spin_button", risk_tier:"high"}, ...}
  round_end_signature        TEXT,                          -- signature_hash that means "ready for next move"
  balance_signature          TEXT,                          -- where to read the wallet
  balance_regex              TEXT,                          -- how to parse it; discovered first-time via OCR/LLM
  bonus_trigger_signatures   TEXT NOT NULL DEFAULT '[]',    -- JSON list
  auto_dismiss_signatures    TEXT NOT NULL DEFAULT '[]',    -- modals to swat without thinking
  recovery_json              TEXT NOT NULL DEFAULT '{}',    -- known failure modes per game
  rules_json                 TEXT,                          -- paytable / paylines / bet limits — read once via intent_observe_rules
  rules_observed_signature   TEXT,                          -- signature_hash of the info screen the rules came from; re-read if it changes
  build_env                  TEXT NOT NULL,
  app_version                TEXT NOT NULL,
  created_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Write paths**:
- First time the agent reaches a `loaded_signature` for a slug, it inserts an empty playbook row. The map-first/LLM-fallback loop fills `actions_json` as it resolves spin/max-bet/etc. selectors via `FindElementWithFallback`.
- Balance: first round on a new table runs an "observe balance" sub-flow (read page-source near the wallet strip → propose regex via LLM → operator confirms via dashboard). After that, `balance_regex` is fixed for this `(slug, build_env, app_version)` until the operator unsets it.
- `intent_observe_rules` (one-shot) reads paytable/paylines once per build/version, persists as `rules_json`.

**Reads**: `intent_load_game_context` injects `game_playbook` row + `game_kinds/<kind>.md` into prompt layer L4.5 on `game_loaded` signature.

---

## 3. Walking the floor — `screen_action_frontier`

For every screen the agent has stood in, a list of controls it has tried (and how often it succeeded), plus controls it has *seen* but not yet pressed. Populated by enumerating interactive elements from page-source on every visit.

```sql
CREATE TABLE IF NOT EXISTS screen_action_frontier (
  screen_sig         TEXT NOT NULL,
  element_id         TEXT NOT NULL,           -- accessibility-id or stable selector key
  attempted_count    INTEGER NOT NULL DEFAULT 0,
  succeeded_count    INTEGER NOT NULL DEFAULT 0,
  last_attempted_at  TIMESTAMP,
  side_effect        TEXT NOT NULL DEFAULT 'idempotent',   -- idempotent|reversible|destructive
  PRIMARY KEY (screen_sig, element_id)
);
```

**Write paths**:
- Every screen visit (post-tap-and-verify): observer parses page-source, computes `element_id` for every visible interactive element, INSERT-OR-IGNORE rows with `attempted_count=0`.
- On every `SmartTap` / `VerifyTap` / `FindElementWithFallback`: increment `attempted_count` and (on success) `succeeded_count`.

**Reads**: `intent_explore` priority queue: unattempted (count=0) > low-success-rate > stale (last_attempted_at old). Destructive edges (operator-classified) are excluded from explore pickup.

---

## 4. Doors that lead to multiple rooms — `transition_outcomes`

Same control on the same screen can lead to different next screens (A/B variants, banner rotation, stochastic prompts). 1-to-N edges, with observation counts.

```sql
CREATE TABLE IF NOT EXISTS transition_outcomes (
  start_sig        TEXT NOT NULL,
  action           TEXT NOT NULL,             -- "tap:spin_button" | "type:search_bar:{query}" | "system_back" | ...
  end_sig          TEXT NOT NULL,
  observed_count   INTEGER NOT NULL DEFAULT 1,
  last_seen        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  edge_kind        TEXT NOT NULL DEFAULT 'tap',   -- tap|back|system_back|swipe_*|longpress|type|scroll|deeplink
  side_effect      TEXT NOT NULL DEFAULT 'idempotent',
  precondition     TEXT,                          -- JSON predicate over RuntimeFacts; null = always reachable
  PRIMARY KEY (start_sig, action, end_sig)
);
```

**Write paths**:
- Auto-recorder (`observer_activity.record_transition_observation`): on every verified tap-and-verify, UPSERT and increment `observed_count`.
- The legacy `screen_transitions` table becomes a SQL view that returns the top-`observed_count` end_sig per `(start_sig, action)`.

**Reads**:
- Path planner (`shared/screen_graph.py`) prefers highest-frequency outcome but knows about the others.
- Report-diff treats distribution shifts as such, not as regressions, below `OUTCOME_DRIFT_THRESHOLD` (default 0.30 relative change).

---

## 5. The night's bets — `game_rounds`

Per-round telemetry. The agent's session ledger.

```sql
CREATE TABLE IF NOT EXISTS game_rounds (
  round_id                TEXT PRIMARY KEY,            -- workflow_id + sequence
  workflow_id             TEXT NOT NULL,
  game_slug               TEXT NOT NULL REFERENCES game_directory(slug),
  started_at              TIMESTAMP NOT NULL,
  ended_at                TIMESTAMP,
  bet_amount              REAL,
  balance_before          REAL,
  balance_after           REAL,
  outcome                 TEXT,                        -- win|loss|push|bonus_trigger|error|timeout
  bonus_round_id          TEXT,                        -- if a bonus was triggered, link to bonus rounds
  evidence_path           TEXT,
  balance_read_attempts   INTEGER NOT NULL DEFAULT 1,  -- per FR-009 retries before halt
  notes                   TEXT
);
CREATE INDEX IF NOT EXISTS ix_rounds_workflow ON game_rounds(workflow_id);
CREATE INDEX IF NOT EXISTS ix_rounds_slug     ON game_rounds(game_slug, started_at);
```

**Write paths**: `intent_play_game` activity emits one row per spin/hand. `intent_play_bonus` writes bonus-frame rounds with `bonus_round_id` linked.

**Reads**: run-report JSON (FR-037), regression-detection diff, BudgetCheck activity (`balance_after` of last row vs `balance_before` of first row).

---

## 6. How long does a spin take? — `animation_timings`

Online-learned wait times per `(game, action, build, version)`. Replaces hardcoded `WaitSeconds(N)`.

```sql
CREATE TABLE IF NOT EXISTS animation_timings (
  game_slug    TEXT NOT NULL,
  action       TEXT NOT NULL,           -- "spin" | "bonus_intro" | "ladder_complete" | "deal_card" | ...
  build_env    TEXT NOT NULL,
  app_version  TEXT NOT NULL,
  samples      INTEGER NOT NULL DEFAULT 0,
  mean_ms      INTEGER,
  m2_ms        REAL,                    -- Welford's running M2 (for stddev online-update)
  stddev_ms    INTEGER,
  p95_ms       INTEGER,
  PRIMARY KEY (game_slug, action, build_env, app_version)
);
```

**Write paths**: `WaitForSignature` activity, on every successful wait, online-updates the row using Welford's algorithm. New `(build_env, app_version)` starts at 0 samples; until 5 samples accumulate, the wait uses the kind file's `learned_default`.

**Reads**: `WaitForSignature` itself (timeout = `p95 + 2σ` when samples ≥ 5).

---

## 7. Stable identity across renovations — `logical_screens` and `logical_elements`

Apps re-skin. Signature hashes change. Logical names don't. Operator-set on promotion.

```sql
CREATE TABLE IF NOT EXISTS logical_screens (
  logical_id      TEXT PRIMARY KEY,        -- e.g. "lobby_home", "slingo_base_grid"
  canonical_name  TEXT NOT NULL,
  description     TEXT,
  is_hub          INTEGER NOT NULL DEFAULT 0,
  staleness_days  INTEGER,                 -- per-surface decay; null = env default
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logical_elements (
  logical_id      TEXT PRIMARY KEY,        -- e.g. "spin_button", "search_bar"
  canonical_label TEXT NOT NULL,
  default_risk_tier TEXT NOT NULL DEFAULT 'low',   -- HIGH for bet/spin/deposit/withdraw/sign-in
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE screen_signatures ADD COLUMN logical_id TEXT REFERENCES logical_screens(logical_id);
ALTER TABLE screen_signatures ADD COLUMN parent_sig TEXT;       -- modals point to their underlying screen
ALTER TABLE screen_signatures ADD COLUMN deprecated_at TIMESTAMP;
ALTER TABLE screen_signatures ADD COLUMN dom_skeleton_hash TEXT;

ALTER TABLE screen_elements ADD COLUMN logical_id TEXT REFERENCES logical_elements(logical_id);
ALTER TABLE screen_elements ADD COLUMN risk_tier TEXT NOT NULL DEFAULT 'low';
ALTER TABLE screen_elements ADD COLUMN side_effect TEXT NOT NULL DEFAULT 'idempotent';
```

**Write paths**: `accept_signature_proposal.py --as <logical_name>` either creates a new logical row or attaches a new signature variant to an existing one.

**Reads**: report-diff aggregates by `logical_id` so "the spin button" is one thing across renovations. Path planner can route via logical hubs.

---

## 8. Provenance — `transition_observations`

Append-only event log behind `transition_outcomes`. Used for review tooling and graph-diff drill-down.

```sql
CREATE TABLE IF NOT EXISTS transition_observations (
  observation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id      TEXT NOT NULL,
  ts               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  start_sig        TEXT NOT NULL,
  action           TEXT NOT NULL,
  end_sig          TEXT NOT NULL,
  build_env        TEXT NOT NULL,
  app_version      TEXT NOT NULL,
  outcome          TEXT NOT NULL,           -- success|verify_fail|timeout|error
  duration_ms      INTEGER
);
CREATE INDEX IF NOT EXISTS ix_obs_workflow ON transition_observations(workflow_id);
CREATE INDEX IF NOT EXISTS ix_obs_pair     ON transition_observations(start_sig, action, ts);
```

**Retention**: 90 days verbatim, then rollup into `transition_outcomes` summary; per-event rows dropped (deferred to Phase E per gaps E1).

---

## 9. The novel-room queue — extensions to `signature_proposals`

```sql
ALTER TABLE signature_proposals ADD COLUMN dom_skeleton_hash TEXT;
ALTER TABLE signature_proposals ADD COLUMN cluster_id TEXT;            -- canonical signature_hash of cluster
ALTER TABLE signature_proposals ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'; -- pending|accepted|rejected
ALTER TABLE signature_proposals ADD COLUMN rejected_cooldown_until TIMESTAMP;
ALTER TABLE signature_proposals ADD COLUMN evidence_path TEXT;
```

The dashboard groups by `cluster_id`; the operator names a canonical and accepts the cluster, or rejects the cluster. Rejected DOM skeletons stay rejected until cooldown expires.

---

## Relationships at a glance

```
game_directory ──< game_playbook                           (one playbook per played game)
game_directory ──< game_rounds                             (the night's ledger)
game_rounds ────  game_rounds (bonus_round_id)             (bonus rounds linked to base round)

logical_screens ──< screen_signatures (logical_id)         (stable name across renovations)
logical_elements ──< screen_elements (logical_id)
screen_signatures ──< signature_proposals (cluster_id)     (novel rooms, dedup'd)

screen_signatures ──< screen_action_frontier               (controls on this screen)
screen_signatures ──< transition_outcomes (start_sig)      (doors leading out)
screen_signatures ──< transition_outcomes (end_sig)        (doors leading in)

transition_outcomes ──< transition_observations (start_sig, action, end_sig)   (provenance log)
animation_timings   keyed by game_slug × action × build × version              (learned waits)
```

## State transitions worth naming

**Proposal lifecycle**: `pending` → `accepted` (logical_id assigned, all hashes in cluster bound, used by next run) | `rejected` (cooldown set; same skeleton suppressed until cooldown expires).

**Element confidence (existing rules, restated)**: starts low → graduates to HIGH (never), MEDIUM (90% conf + 5 uses), LOW (80% conf + 3 uses) per Constitution V. **Graduated → degraded**: 3 consecutive failures auto-demote one tier (forces re-verify on next attempt) per FR-027; 5 failures flag for operator review.

**Game session**: `parse_session` → `authenticate` → `navigate_to_game` → `load_game_context` → `play_game (loop)` ↘ `play_bonus (sub-loop)` ↗ → `report` (terminal). Plan-graph YAML in `graphs/casino_session.yaml` is the source of truth.

**Budget**: `MAX_LOSS_USD` (env, hard ceiling) ⩾ `prompt.budget.max_loss_usd` (lowering only). First-of: max-loss | max-spins (default 20) | max-minutes (default 10) wins. Recorded in `game_rounds.outcome` and run-report `terminal_reason`.

## Validation rules (mapped to FRs)

- **FR-002**: resolver reads `game_directory` only; never the playbook.
- **FR-003, FR-004**: BudgetCheck activity computes `effective_max_loss = min(env_max_loss, prompt_max_loss or env_max_loss)`; never `max(...)`.
- **FR-009**: `intent_load_game_context` reads `game_playbook` row + `game_kinds/<kind>.md`; if no playbook row exists yet, kind file alone (insert empty playbook row).
- **FR-018, MW-1, MW-2**: every verified tap → `transition_outcomes` UPSERT + `transition_observations` INSERT; every `FindElementWithFallback` hit → `screen_elements` UPSERT.
- **FR-019, FR-020, MW-3**: stored confidence read-only at runtime; effective confidence at read time per (build_env, version, staleness_days).
- **FR-021**: `animation_timings` ignored at read time when (`build_env`, `app_version`) ≠ current; existing samples preserved as history.
- **FR-022**: `transition_outcomes` 1-to-N; report-diff threshold `OUTCOME_DRIFT_THRESHOLD`.
- **FR-024**: loop detector: `transition_observations.start_sig` count grouped by workflow_id over last 20 events ≥ 5 → trigger BackOff.
- **FR-025, FR-029, FR-030**: `signature_proposals.cluster_id` + `status` + `rejected_cooldown_until`; dashboard reads from clusters.
- **FR-027**: tracked in `screen_elements.consecutive_failures` (new column added below).

```sql
ALTER TABLE screen_elements ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0;
ALTER TABLE screen_elements ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0;
```

- **FR-031, FR-032**: enforced in `prompts/generators.py` (T0 strip) and `_normalize_result` in `activities/tool_activities.py` (the *callers*; the frozen file itself is **not** modified — the tier classifier moves to `activities/observer_activity.py` which already wraps result post-processing). *(Re-evaluation: this might require a small WF-3-allowed touch to `tool_activities.py`. Plan to validate during implementation.)*

## Migrations

All schema additions are idempotent `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` (silently ignored on re-run). Applied at worker boot in `shared/screen_map_db.py::ensure_schema()`. No external migration tooling required.

## What this model does NOT contain

(Explicit, to keep the no-hardcoding mandate visible.)

- No `play_loop_json` *content* hardcoded for any game. The schema column exists; rows are populated by play.
- No selectors, coordinates, or regexes per game in any seed file.
- No animation waits as constants in code.
- No phase prose, action sequences, or tool descriptions in DB or seed files.
- No env-specific paths, build IDs, or app packages — those live in `RuntimeFacts` derived from `select_device` at runtime.
- No skills primitive (decided dropped earlier in the design conversation; multi-step recipes are paths through the screen-graph via parameterized transitions).
