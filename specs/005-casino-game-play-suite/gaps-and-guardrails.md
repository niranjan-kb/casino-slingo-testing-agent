# Gaps & guardrails — production-hardening layer

Companion to the four design docs. Captures architectural gaps and operational bottlenecks surfaced in cross-doc review. These are the things that protect the system from silent corruption, operator overload, and replay non-determinism once volume goes up. Each item names the doc(s) it patches.

## A. Schema & semantics

### A1. Per-(build_env, app_version) keying for learned values
Patches: scaling §5; complete-screengraph §3.

`animation_timings` is keyed by `(game_slug, action)` only — a build bump silently averages new animations against old samples. Already fixed in scaling §5: PK now `(game_slug, action, build_env, app_version)`. Apply the same rule everywhere a learned scalar is stored — currently only `animation_timings`, but extend on contact: `transition_outcomes` distributions, `balance_read_confidence`, etc.

### A2. Per-surface decay
Patches: self-improving-loop §"Decay and safety".

`SCREEN_MAP_STALENESS_DAYS=30` is global. Lobby/promo screens churn weekly; auth screens are stable for months. Add `screen_signatures.staleness_days` (nullable; falls back to env). Set on operator promotion. Suggested defaults:
- auth, settings, KYC: 90d
- in-game (base grid, paytable): 60d
- lobby home, category lobbies: 14d
- promo banners, "what's new", recommendations strips: 7d

`is_hub` and `parent_sig` (overlays) inherit the parent's value.

### A3. Stochastic outcomes — full migration plan
Patches: complete-screengraph §2.

Today: `screen_transitions(start_sig, action, end_sig, conf)` — 1-to-1.
Target: `transition_outcomes(start_sig, action, end_sig, observed_count, last_seen)` — 1-to-N.

Migration:
1. Add `transition_outcomes` table; backfill from `screen_transitions` (one row each).
2. Update auto-recorder to UPSERT into `transition_outcomes` instead of `screen_transitions`.
3. Path planner: when an edge has multiple outcomes, pick the highest-frequency one; still use `effective_confidence` decay.
4. Report-diff: an outcome appearing/disappearing is a **distribution shift**, not a regression. Threshold: ≥30% relative change in count over the last N runs. Below threshold = noise.
5. `screen_transitions` becomes a deprecated view (UNION over outcomes' top picks) until callers migrate.

### A4. Edge preconditions — wire into the planner contract
Patches: scaling §8; complete-screengraph §2.

Screengraph proposes `precondition` JSON over RuntimeFacts. Without wiring, exploration in NJ proposes MA-only edges and report-diffs flag false regressions.

- Path planner filters edges by `eval(precondition, RuntimeFacts)` at query time.
- Planner prompt L4 (graph state) only lists reachable next-edges given current facts.
- Report-diff ignores edges that became unreachable due to facts change (jurisdiction switch, flag flip).

### A5. ReadBalance retries before halt
Patches: scaling §7.

OCR/regex on a transient frame fails routinely. Today the workflow halts after N failed reads. Add per-game `balance_read_confidence`; on miss, retry `min(3, ceil(1/conf))` times with 500ms spacing before declaring "balance unknown → halt." Log every retry to `game_rounds.balance_read_attempts`.

### A6. Bonus novelty — bounded explore-in-bonus
Patches: scaling §11 Phase D2.

`intent_play_bonus` triggers on a known `bonus_trigger_signature`. A new bonus mini-game has no signature → cold start. Add `intent_explore_in_bonus`:
- Frozen wager (no further bets accepted while in bonus mode).
- Max actions cap (e.g., 30 taps).
- Exit-detection: if exits to base grid signature, success; if stuck, save evidence + force-exit via system_back.
- Real-money risk during bonus exploration is bounded by *not betting*, not by budget — the wager already happened; we're just observing the payout.

### A7. Failure → auto-demote, not halt-forever
Patches: manual-intervention-and-maintenance "Per-incident"; self-improving-loop "Decay and safety".

Today: 5 failures on one screen → SaveEvidence + halt. Single failure on a HIGH-tier graduated row → confidence reset.

Missing: when a graduated coordinate is *wrong* (UI drifted), every future run halts. Add **auto-demote**:
- 3 consecutive failures on a graduated row → confidence drops one tier (HIGH→MEDIUM→LOW), forcing re-verification on next attempt instead of deterministic tap.
- 5 failures → row flagged `needs_review=true` (not deleted); operator sees it in next daily triage.
- Halt only after auto-demote + LLM fallback + verify all fail.

This converts hard failures into self-healing degradations.

### A8. Modal/overlay nesting
Patches: complete-screengraph "Smaller gaps"; scaling §3 sub-strategies.

Add `screen_signatures.parent_sig` (nullable). Modals/drawers/sheets point to the screen they overlay. Path planner: `dismiss_overlay` is a special edge kind that pops to parent. Useful for "permission stack" navigation today and for any modal-heavy flow tomorrow.

## B. Replay & determinism

### B1. Temporal replay vs. LLM non-determinism
Patches: CLAUDE.md "Why Temporal" — assumption was implicit.

Temporal replays activities deterministically; the planner LLM call is non-deterministic. Cache miss on replay → divergent decisions → divergent history. The current architecture **already** fences this: the planner LLM call lives in a single activity (`agent_toolPlanner`); the activity result is stored in workflow history; replay reads the stored result, never re-calls Anthropic.

Document this explicitly:
- The planner activity is the **only** non-deterministic boundary.
- On replay, we never re-invoke the LLM — we replay the captured `plan_next_action` tool-use response from history.
- If prompt-cache changes alter latency or cost, behavior is unaffected because behavior is sourced from history, not from re-execution.

### B2. Cache invalidation for L0+L1 (Anthropic prompt cache)
Patches: setup §5; scaling Phase A2.

Anthropic's `cache_control: ephemeral` is keyed on prefix exactness. Cache must bust when:
- Worker restarts (fresh process loses TTL anyway — no action).
- `prompts/persona/soul.md` changes (rebuild + worker restart).
- Tool registry changes (new tool, new arg) — same.
- Intent registry changes — same.
- `appium-mcp` version changes (tool descriptions ride along) — same.

Practical rule: **any deploy that ships new bytes to the worker busts the cache automatically** (process restart). No explicit invalidation API needed. Document it so nobody adds long-lived in-memory caches that survive a soul change.

## C. Backpressure & operator throughput

### C1. Operator throughput as the binding constraint
Patches: manual-intervention-and-maintenance — add cap.

Daily triage + weekly diff + monthly grooming + per-release re-seed grows with `games × builds × jurisdictions`. Cap operator load explicitly:

```
proposals_per_week_budget: 50
on_exceed:
  - explore mode auto-throttles (ε from 0.10 → 0.02)
  - exploration runs disabled until backlog < 30
  - alert "operator queue saturated"
```

Without a cap, the agent will produce more work than humans can review and the gate breaks down silently.

### C2. Signature-proposal dedup
Patches: complete-screengraph §1; manual-intervention "Daily".

A noisy build with rotating banners or A/B variants can produce O(100s) of near-duplicate hashes. Add cluster-by-DOM-skeleton:
- `signature_proposals.dom_skeleton_hash` — hash of the page-source with text/images stripped, leaving only element types + hierarchy.
- Triage tool groups by skeleton; operator sees ~10 clusters instead of 100 hashes.
- Within a cluster: pick canonical, mark others as "dom_variant_of: <canonical>".

Without this, noisy releases overwhelm the gate.

### C3. Cache-miss kill-switch for nav search
Patches: scaling §3, §11 Phase A.

Search-bar path = 4 LLM turns. Phase A claim ("cache makes turns cheap") is a **hypothesis**. Measure on first deploy:
- Cache hit rate on L0+L1 over a 100-turn window.
- If <85%: kill-switch flips to "search via skill-replay" (the Skills primitive we deferred — keep the option in the back pocket).
- Threshold + kill-switch behavior live in env vars, not code.

### C4. Explore budget on cert / prod-spectator
Patches: complete-screengraph §1 budget guard.

`max_balance_loss` doesn't apply on cert/prod-spectator (no real money). The actual constraint is:
- Wall-clock minutes per session (e.g., 30m)
- Novel-screen API rate (don't hammer support endpoints)
- Total taps per session (e.g., 500 — emulator throughput cap)

Use whichever bound binds first; report which.

## D. Quality assurance for the QA agent

### D1. Resolver eval set
Patches: scaling §2.

Fuzzy matcher silently routing `"blackjack"` → `"black gold slots"` would be invisible. Add:
- `tests/resolver_cases.yaml` — 50+ canonical queries with expected `slug`.
- `pytest tests/test_resolver.py` — runs on every PR.
- New game added → at least 3 query variants added (full name, abbrev, common typo).

### D2. game_kinds KB drift detector
Patches: manual-intervention "Monthly"; scaling §4.

`game_kinds/<kind>.md` is in the planner prompt every game turn but reviewed monthly. Drift between KB prose and actual behavior inflates planner error.

- After every play run, check: did each `key_signatures` listed in the kind's KB actually appear in the run? If not, increment `kind_kb_misses[kind][signature]`.
- Threshold: signature listed but unseen for 5 consecutive runs → flag for KB update.
- Conversely: signatures observed but not listed → propose addition.

Surfaces in run report; manual review still gates the edit.

### D3. Token-reduction measurement
Patches: setup-before-scalling "Headline numbers"; scaling Phase A.

The 80% claim from setup-doc is theoretical. Commit to a measurement:
- `observation_log` already records per-turn input/output tokens.
- Dashboard: rolling 7-day p50/p95 input tokens per turn, by goal × intent.
- Regression alert: 7d p50 grows >20% week-over-week → block deploy.

## E. Smaller fixes

### E1. `transition_observations` retention
Patches: complete-screengraph §4.

Append-only at 200 screens × 50 actions × N runs/day grows unboundedly. Rule: **rollup ≥ 90d into summary rows** (count + first/last seen + outcome distribution); drop the per-event rows. Operator review tool reads from summary; raw events available for debug for 90d only.

### E2. Loop detector consolidation
Patches: scaling §8 guards; self-improving-loop "Steady-state economics"; complete-screengraph §1.

"Same screen 5× in 20 steps" is mentioned once but not unified. Single rule, applied everywhere:
- Activity-side counter on `current_signature` per intent.
- 5 visits in 20 actions → `BackOff` activity: pop overlays, system_back twice, re-evaluate.
- Still looping after backoff → SaveEvidence + terminate intent (route to next reachable per plan-graph).

The "23-turn login → ~0 LLM" steady state assumes no loops; the detector keeps that assumption honest.

### E3. DB write-lock during operator scripts
Patches: manual-intervention "Per-incident".

"Never edit the DB to fix a run in flight" is right but unenforced. SQLite supports advisory locking via a `meta` row. Operator scripts (`accept_signature_proposal.py` et al.) take a write lock; worker checks the lock at activity start and aborts the activity (Temporal retries) if held. Operator finishes → releases. No race possible.

## F. Naming & deprecation

### F1. `intent_navigate_to_screen` → `intent_navigate_to_game`
Patches: spec-004; CLAUDE.md; scaling §1a.

Spec-004 introduced `intent_navigate_to_screen`. Scaling adds `intent_navigate_to_game`. Migration: `intent_navigate_to_game` is the play-flow specialization; `intent_navigate_to_screen` stays for non-play targets (settings, account, support). Both load from `intents/`. After Phase C ships, audit which goals still reference the generic version; remove if none.

### F2. Table-name standardization
Patches: self-improving-loop diagrams (already fixed).

Always use `screen_signatures` / `screen_elements` / `screen_transitions` — never the bare nouns. Prevents grep collisions with code that has `signatures` for crypto, `transitions` for UI animations, etc.

---

## Phasing

These map onto the existing phase plan in scaling §11:
- **Phase A** picks up: B1 (document), B2 (document), C3 (instrument), D3 (instrument), F1 (deprecate), F2 (rename — done).
- **Phase B** picks up: A4 (precondition wiring), A8 (parent_sig), C2 (proposal dedup), D1 (resolver eval).
- **Phase C** picks up: A5 (ReadBalance retries), C4 (cert explore budget), E2 (loop detector unification).
- **Phase D** picks up: A1 (already in scaling), A3 (stochastic outcomes migration), A6 (bonus exploration), A7 (auto-demote), D2 (KB drift).
- **Phase E** picks up: A2 (per-surface decay), C1 (operator cap), E1 (retention), E3 (DB lock).

Nothing in this doc invalidates the four design docs; everything tightens or makes explicit what was implicit.
