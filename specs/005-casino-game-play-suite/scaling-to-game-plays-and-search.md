# Scaling beyond auth-POC — vague prompts → search/navigate → game-context injection → bounded play, with on-the-fly learning

Companion to `setup-before-scalling-to-game-plays-search.md`. That doc inventories per-turn context bloat and hardcoding in the auth POC. This doc is the scaling plan: how the same primitives extend to vague-prompt interpretation, lobby search, automatic per-game context injection, budgeted play, and on-the-fly learning of complex game mechanics.

## 0. The user-journey, mapped to existing primitives

```
"play slingo"
   │
   ▼
ParseSessionIntent  ──▶  SessionIntent{flow:play, target:{kind?:any, query:"slingo"}, budget:{max_loss_usd:env}}
   │
   ▼
PlanGraph (compiled from SessionIntent — see prior doc §7)
   ├─ intent_authenticate          (already locked)
   ├─ intent_navigate_to_game      (RENAMES today's intent_navigate_to_screen — see §1a)
   │     └─ recents → category → search-bar → scroll       (sub-strategies, first hit wins)
   ├─ intent_load_game_context     (NEW — auto-inject game/kind KB)
   ├─ intent_play_game             (already drafted)
   │     └─ intent_play_bonus      (NEW sub-intent on bonus_trigger)
   └─ intent_report
   ▼ guarded throughout by ▼
BudgetGuard  (reads RuntimeFacts.constraints.max_loss_usd from env)
```

Every box is either an existing intent file, a new intent file, or a small activity. **No new workflow code paths** — the workflow stays the single `AgentGoalWorkflow`, intents are markdown, mechanics are data.

## 1. Prompt compiler — `intent_parse_session`

Same pattern as the planner: tool-use forcing on a synthetic `parse_session_intent` tool. Runs **once** at session start, before authenticate.

**Schema** (closed-set where possible):
```jsonc
{
  "flow":   "enum[play, navigate, audit, observe, report_only]",
  "target": {
    "kind":  "enum[any, slots, slingo, blackjack, roulette, live_dealer, table, scratch]?",
    "query": "string?",          // free text the resolver disambiguates
    "slug":  "string?"           // if user gave an exact catalog slug
  },
  "budget": {
    "max_loss_usd":   "number",  // default ← env MAX_LOSS_USD
    "max_spins":      "integer?",
    "max_minutes":    "integer?"
  },
  "terminal": "enum[budget_exhausted, target_balance_delta, n_spins, user_signal, report]"
}
```

**Examples**:
- `"play slingo"` → `{flow:play, target:{kind:slingo, query:"slingo"}, budget:{max_loss_usd:env, max_spins:20}, terminal:n_spins}`  *(default-bounded — see budget rules below)*
- `"play any slot for 5 minutes"` → `{flow:play, target:{kind:slots}, budget:{max_minutes:5}}`
- `"open the lobby and tell me what changed"` → `{flow:audit, terminal:report}`

**Where**: `intents/intent_parse_session.md` + `tools/slingo_qa/ParseSessionIntent.py`. Stored on the workflow as `state.session_intent` (queryable, like other intent state today).

**Budget authority — env is the ceiling, prompt can only lower it**:
- `MAX_LOSS_USD` env var sets the **hard ceiling** at worker startup. The agent cannot raise it.
- A prompt-supplied `budget.max_loss_usd` is treated as `min(env_ceiling, prompt_value)` — never `max(...)`.
- Vague prompts get **default bounds** even when not stated: `max_spins=20` AND `max_minutes=10` AND `max_loss_usd=env_ceiling`. First terminal hit wins. Without these defaults, an accidental `"play slingo"` would drain the full env budget.
- A prompt may specify a **stricter** terminal (e.g., `"play 5 spins"`); never a looser one.

**`intent_navigate_to_screen` deprecation**: `intent_navigate_to_game` supersedes the spec-004 generic navigator for the play flow. Other flows (audit, observe) still use the generic version. Migration: `intent_navigate_to_screen` becomes a thin wrapper that delegates to `intent_navigate_to_game` when target is a game; remove after Phase C ships.

## 2. Resolver — `target.query` → catalog row(s)

Pure SQLite, no LLM:
1. Exact `slug` match.
2. `kind` filter + fuzzy name match (sqlite `LIKE` + token-set ratio).
3. Rank by `popularity DESC, last_played_at DESC`.
4. K=0 → mark `unresolved=true` → triggers search-bar branch in `intent_navigate_to_game`.
5. K=1 → done.
6. K>1 → take top match; record alternatives in `state` so the report can list them.

**Two-table split — superseded by [data-model.md](./data-model.md) §1–§2**:

- `game_directory` (per-game, pre-launch availability): slug, display_name, kind, aliases_json, popularity, available, loaded_signature, last_seen_in_lobby_at, last_played_at, build_env, app_version. Populated by lobby-walk discovery or ops seed.
- `game_playbook` (per-game, post-launch knowledge): slug FK, actions_json, round_end_signature, balance_signature, balance_regex, bonus_trigger_signatures, auto_dismiss_signatures, recovery_json, rules_json. Auto-populated on first launch.

The resolver reads `game_directory` only. Auto-context injection reads `game_playbook` (when present) + `game_kinds/<kind>.md`.

## 3. `intent_navigate_to_game` — search as a real branch, not improvisation

Today's `intent_navigate_to_screen` is one declarative end-state. For game discovery we want **ordered sub-strategies** with first-success-wins, all backed by the screen-graph:

```yaml
# intents/intent_navigate_to_game.md (frontmatter)
sub_strategies:
  - name: recents
    precondition: catalog.last_played_at within 7d
    target_signature: lobby_recents_strip + tile[slug]
  - name: category_jump
    precondition: catalog.kind known
    target_signature: lobby_category[kind] + tile[slug]
  - name: search
    target_signature: lobby_search_results + tile[slug]
    via: seeded transitions        # tap search → type {query} → tap first result; each step is a row in screen_transitions
  - name: scroll_grid
    target_signature: lobby_main_grid + tile[slug]
    cap: 20_screens
on_unresolved_query:
  - search                          # query goes into search-bar literally
  - then surface "found these alternatives" via report
```

Each strategy is just a `(start_signature → end_signature)` path the screen-graph already plans. Search is a 3-transition path with a parameterized `type {query}` step — no separate skill abstraction needed.

## 4. Auto game-context injection — `intent_load_game_context`

Triggered on `game_loaded[slug]` signature. Pulls **two** layers, both small:

**Per-game record** (`game_playbook` row, auto-populated on first launch):
```jsonc
{
  "actions": {
    "spin":    { "selector_label": "spin_button", "risk_tier": "high" },
    "max_bet": { "selector_label": "max_bet_button" },
    "info":    { "selector_label": "info_button" }
  },
  "round_end_signature": "spin_idle",
  "balance_signature":   "wallet_strip",
  "balance_regex":       "\\$([0-9.,]+)",
  "bonus_trigger_signatures": ["bonus_intro", "free_spins_intro"],
  "auto_dismiss_signatures": ["network_glitch_modal", "session_keepalive"]
}
```

**Per-kind KB** (`game_kinds/<kind>.md`, ≤400 tokens):
```yaml
# game_kinds/slingo.md
name: slingo
turn_structure: [bet_set, spin, draw, mark_grid, evaluate_pattern, ladder_progression]
typical_animations:
  spin_to_idle_ms: { learned_default: 4500 }
  bonus_intro_ms:  { learned_default: 8000 }
key_signatures: [base_grid, bonus_intro, ladder_complete, free_spin_grant]
recoverable_modals: [low_balance, geo_warning, session_renewal]
```

These two layers compose into **L4.5 game-knowledge** in the planner prompt assembly (insert between L4 graph state and L5 working memory in the prior layering). Kept under ~600 tokens combined; when not in a game, L4.5 is empty.

## 5. On-the-fly learning — what gets written each round

The current observer auto-records `screen_transitions` on every successful tap. Extend with **round-grain telemetry** so the agent learns animation timings and outcome distributions per game:

**Schema additions**:
```sql
ALTER TABLE screen_transitions ADD COLUMN duration_ms INTEGER;
ALTER TABLE screen_transitions ADD COLUMN game_slug   TEXT;
ALTER TABLE screen_transitions ADD COLUMN round_id    TEXT;

CREATE TABLE game_rounds (
  round_id      TEXT PRIMARY KEY,
  game_slug     TEXT,
  started_at    TIMESTAMP,
  ended_at      TIMESTAMP,
  bet_amount    REAL,
  balance_before REAL,
  balance_after  REAL,
  outcome       TEXT,        -- win|loss|push|bonus_trigger|error
  evidence_path TEXT
);

CREATE TABLE animation_timings (
  game_slug     TEXT,
  action        TEXT,        -- spin, bonus_intro, ladder_complete
  build_env     TEXT,        -- test|cert|prod — different builds have different animations
  app_version   TEXT,        -- bump invalidates samples
  samples       INTEGER,
  mean_ms       INTEGER,
  stddev_ms     INTEGER,
  p95_ms        INTEGER,
  PRIMARY KEY (game_slug, action, build_env, app_version)
);
-- On build_env or app_version mismatch at read time: ignore the row (mirror the ×0.5 confidence rule).
-- On version bump: rows for prior version stay (history) but are not used until enough samples accumulate on the new version. Until then, fall back to per-kind learned_default + stable-UI detector.
```

**Learned wait** (instead of fixed `WaitSeconds`): `WaitForSignature(action='spin', timeout=p95+2σ, fallback=stable_ui_detector)`. Online update: each round contributes one sample.

**Novel sequence handling**: when the LLM resolves a sequence the screen-graph couldn't plan (e.g., a new bonus mini-game), each step's `(start_sig, action, end_sig)` is recorded as ordinary `screen_transitions` rows (and any new screens as `signature_proposals`). On re-encounter the path planner finds them automatically — no separate "skill" primitive.

**Rule discovery (cheap)**: on first encounter of `info_screen` for a game, run `intent_observe_rules` once: read paytable / paylines / bet limits via OCR or accessibility tree. Persist to `game_playbook.rules_json`. Don't re-run unless `info_screen.signature_hash` changes.

## 6. Multi-step flows — done by parameterized transitions, not a skills table

Multi-step recipes (search a lobby, dismiss a permission stack, change bet, trigger autoplay, exit a bonus) are just **paths** through the screen-graph. The path planner already plans them; no separate `screen_skills` primitive needed.

What's required:
- **Parameterized actions** on transitions: `screen_transitions.action_template` accepts `{query}`, `{amount}`, etc., supplied by the active intent.
- **Stable signatures only** — don't fingerprint transient frames (typing animations, fade-ins). Signature on stable end-states (search bar focused, search results loaded) so the path stays clean.
- **One source of truth**: signatures + transitions. Two surfaces (signatures and skills) would diverge in practice and double the operator queue.

Cost of this choice: a 4-step flow is 4 planner turns instead of 1 "execute skill" call. After Phase A (cached prefix + tiered history) per-turn cost is ~constant, so 4 cheap turns is fine. Add an explicit skill primitive only if a hot flow shows up that has no stable signatures *and* can't be refactored to expose them.

## 7. Budget guard — `MAX_LOSS_USD` from env

`RuntimeFacts.constraints.max_loss_usd ← os.environ["MAX_LOSS_USD"]` at workflow start. Two enforcement points:

1. **Pre-spin** (`BudgetCheck` activity): `(balance_now - balance_session_start) <= -max_loss_usd` → return `terminate`. Workflow routes to `intent_report`.
2. **Hard ceiling** (workflow guard): if for any reason balance read fails for N rounds, treat as terminate, save evidence, route to report. (Failing safe is non-negotiable for a real-money client even though we run on cert.)

`ReadBalance` activity: page-source extract via `game_playbook.balance_signature` + `balance_regex`. Store every read in `game_rounds.balance_before/after`. Mismatch (e.g., negative bet without round) → save evidence + halt.

## 8. Plan graph (concrete YAML for the casino-session goal)

```yaml
# graphs/casino_session.yaml — drives the workflow's reachable-intent guard
nodes:
  parse_session:    { intent: intent_parse_session, terminal_on_fail: report }
  authenticate:     { intent: intent_authenticate,  requires: parse_session.success }
  navigate_to_game: { intent: intent_navigate_to_game, requires: authenticate.success,
                      input_from: session_intent.target }
  load_context:     { intent: intent_load_game_context, requires: navigate_to_game.success }
  play_game:        { intent: intent_play_game, requires: load_context.success,
                      repeat_until: budget.terminal }
  play_bonus:       { intent: intent_play_bonus, trigger: bonus_trigger_signature,
                      returns_to: play_game }
  report:           { intent: intent_report, requires: any_terminal }
guards:
  budget: { activity: BudgetCheck, after: each_play_round }
  stuck:  { activity: SaveEvidence, after: 3_failures_same_screen, terminate: false }
  panic:  { activity: SaveEvidence, after: 5_failures_same_screen, terminate: true, route: report }
```

The workflow's "active_intent must be reachable" guard (prior doc §7) reads this YAML.

## 9. Vague-prompt → resolver → search-fallback example trace

User: `play slingo`

| # | Activity | Output |
|---|---|---|
| 1 | `ParseSessionIntent` | `{flow:play, target:{query:"slingo", kind:slingo}, budget:{max_loss_usd:50}}` |
| 2 | resolver (SQL) | 3 hits: `slingo_classic`, `slingo_riches`, `slingo_extreme`; pick `slingo_classic` (highest popularity, last_played 2d ago) |
| 3 | `intent_authenticate` | already locked |
| 4 | `intent_navigate_to_game(slug=slingo_classic)` | tries `recents` first; if `lobby_recents_strip+tile[slingo_classic]` is in screen-graph, ~1 LLM turn |
| 5 | …recents miss → `category_jump(kind=slingo)` | navigate to slingo category, find tile |
| 6 | …category miss → `search` path | tap search → type "slingo" (parameterized transition) → tap first result |
| 7 | `game_loaded[slingo_classic]` signature | trigger `intent_load_game_context` |
| 8 | context inject | L4.5 = catalog row + `game_kinds/slingo.md` |
| 9 | `intent_play_game` loop | each round: ReadBalance → BudgetCheck → SmartTap(spin) → WaitForSignature(round_end, p95) → record outcome |
| 10 | bonus_trigger fires | switch to `intent_play_bonus` until back to base game |
| 11 | budget exhausted | route `intent_report` |

**Notice**: every step here corresponds to a row in the DB (catalog, signature, transition, round, timing) — not a Python branch. New games change rows, not code.

## 10. Hardcoding inventory — additions specific to game-play

Builds on prior doc §11. New items now in scope:

| Hardcoded today (or about to be) | Move to |
|---|---|
| `MAX_LOSS_USD` | env → `RuntimeFacts.constraints.max_loss_usd` (already env-only — keep, just thread it) |
| Animation waits (`WaitSeconds(5)`) in any future `play_loop_json` | `animation_timings` table + `WaitForSignature` |
| Game-specific "press spin then wait" prose | `play_loop_json.actions` |
| Per-kind rules baked in prompts | `game_kinds/<kind>.md` (≤400 tokens) |
| Search-bar tap-and-type sequence | seeded `screen_transitions` (3 rows) with parameterized `type {query}` action |
| Permission-stack dismissal | seeded `screen_transitions` (one per permission modal) |
| Bonus-game flow per game | `play_loop_json.bonus_handlers` + `intent_play_bonus` |
| Balance parsing ("$N.NN") | `game_playbook.balance_regex` per game (most share `\$[0-9.,]+`); discovered first-time via OCR/LLM, never code-coded |

## 11. Phased delivery (90-day, ordered, each step independently shippable)

**Phase A — wiring (lands the prior doc's three tactical wins; unblocks everything below)**
A1. `_normalize_result` strips T0 (page-source) from history.
A2. Anthropic prompt caching on L0+L1.
A3. Conversation-history compactor (last-N verbatim + 1-line summaries).
A4. RuntimeFacts envelope; `MAX_LOSS_USD` threads in here.

**Phase B — vague-prompt + resolver + search**
B1. `intent_parse_session` + `ParseSessionIntent` tool.
B2. `game_directory` + `game_playbook` tables (per data-model §1–§2); optional ops seed for ~20 known marquee games into directory only.
B3. `intent_navigate_to_game` with `recents → category → search → scroll` ordered sub-strategies.
B4. Parameterized `screen_transitions.action_template` (e.g., `type {query}`) + seed the search path (search-tap → search-focused → results-loaded → result-tap).

**Phase C — auto-context injection + first real game-play**
C1. `intent_load_game_context` + L4.5 game-knowledge layer in `prompts/generators.py`.
C2. `game_kinds/slingo.md`, `game_kinds/slots.md`.
C3. `play_loop_json` schema (actions, round_end_signature, balance, bonus_trigger, auto_dismiss).
C4. `intent_play_game` minimal loop: ReadBalance → BudgetCheck → action → WaitForSignature → record_round.
C5. `BudgetCheck`, `ReadBalance` activities; `game_rounds` table.
C6. End-to-end on `slingo_classic` (target POC: 20-spin run, $50 loss cap, full report).

**Phase D — on-the-fly learning + complex games**
D1. `animation_timings` table + `WaitForSignature` learned-wait.
D2. `intent_play_bonus` sub-intent + workflow trigger on `bonus_trigger_signature`.
D3. `intent_observe_rules` (one-shot rule discovery on info screens).
D4. Second game kind (slots — Cleopatra-style), validate kind-KB reuse.
D5. Third kind (a Slingo with bonus mini-game — validates `intent_play_bonus` and that novel sub-flows fall out of plain transitions).

**Phase E — operability**
E1. Run-report JSON (rounds[], outcomes, animation_timings deltas, signatures_proposed, regressions).
E2. CI diff against last main run.
E3. Cost dashboard from `observation_log`.

After Phase C, "play slingo" works end-to-end on Android cert with budget. After Phase D, complex games (with bonus rounds + variable timing) are first-class. After Phase E, this is a tool the QA org uses on every PR.

## 12. What to explicitly **not** build yet

- iOS / web drivers — the platform-as-first-class work in the prior doc. Same architecture, but only after Phase D works on Android.
- Compliance / a11y / localization audits — separate goals, not in this scaling arc.
- Live dealer (network-time-pressured games) — different latency model; defer to v2.
- Auto-promotion of signatures — keep operator-gated (FR-022).
- Multi-account orchestration — single account at a time until budget guard is proven.
