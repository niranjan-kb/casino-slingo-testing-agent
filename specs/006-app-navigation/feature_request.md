# Feature Request 006 — Reliable game-find + general app navigation

**Status**: Draft  
**Owner**: Casino QA Agent (Danny Ocean)  
**Predecessor**: 005-casino-game-play-suite (US1 in flight)  
**Successor**: 007-reliable-play (TBD)

---

## tl;dr

Danny can now authenticate reliably. The next critical capability is **game-find** — going from a vague operator prompt (`play any blackjack`) to a loaded game surface. Today this fails because (a) `intent_navigate_to_game` short-circuits on `ResolveDirectory unresolved` without trying the documented fallback chain, and (b) Danny has no mental map of where things live in the casino app (recents, search, categories, bottom nav, daily-spin entry point). This delivery closes both gaps.

---

## Problem statement

T052 v9 (run `86fc0d35-b3c7-4ac6-b8dc-226d46185151`, 2026-05-14) ran the four-intent chain — parse_session ✓ → authenticate ✓ → navigate_to_game ⚠️ → report ❌ — without crashing. But:

- **`intent_navigate_to_game` made only 4 planner emissions** before giving up: screenshot → DetectScreen → page_source → `next=done`. **Zero taps** on recents/category/search/scroll. The agent's terminal rationale claimed *"exhausted all four strategies"* — that was a hallucinated justification.
- **`game_directory` rows = 0** after the run despite the agent crossing the lobby. The lobby-walk auto-discovery (T046) silently no-op'd because:
  - `home` is not in `_LOBBY_SCREEN_IDS` (the casino app's actual lobby screen id)
  - Fanatics' real tile resource-ids (`casino game component tile`, `small_game_component`) are not in `_TILE_ID_SUBSTRINGS`
- **Danny has no app-structure prompt.** The kind files describe how to PLAY each kind. The intent file describes a fallback chain. Nothing tells Danny where the recents tab IS, where the search bar IS, what categories exist and which kinds they contain.

Net effect: even after the spec-005 prompt-stack hardening, game-find is the single biggest gating step between login and any post-auth user story.

---

## Why this matters

Game-find is on the critical path for every downstream intent:

- `intent_load_game_context` needs a loaded game
- `intent_play_game` needs `actions_json` from the playbook
- `intent_report` needs rounds in `game_rounds`
- `intent_play_bonus` only fires from inside a game

Without reliable game-find, every user story past US1's auth segment is structurally blocked.

---

## Scope (in)

### 1. `prompts/persona/app_structure.md` (new)

Danny's mental map of the Fanatics Casino app. Target: ≤800 tokens (L0-adjacent layer, cacheable, written once, read every turn). Content:

- **Bottom nav** — Home / Jackpots / Daily Spin / Invite $$ / Rewards. What each does, what "Daily Spin" actually maps to (FanCash Spins, daily-bonus feature; per [fancash_spins.md](../../fancash_spins.md)).
- **Lobby layout** — top header, category pill row, search input, FanCash banner, recently-played strip (if visible to the agent's account), main game grid.
- **Category pill → kind mapping** — answers "if kind=blackjack, which pill should I try?". Likely "Table Games" and/or "Live Dealer".
- **Search behaviour** — does it autocomplete, what query format works, does it filter or navigate.
- **The "load progression"** — lobby → tile tap → loading screen → game-ready signature (the canonical visual sequence for one representative game).
- **Universal modals** — geo prompts, responsible-gaming reminders, "are you still there?" timeouts, FanCash conversion offers. Default action per modal.
- **Deposit-avoidance reinforcement** — *"You NEVER tap Deposit / Add Funds / Withdraw / Convert FanCash / KYC submit"*. Cross-cutting policy, currently only in [user.md](../../goals/casino_session/prompts/user.md). Reinforced here because it's a navigation-time rule.
- **State/jurisdiction reminder** — *"if `RuntimeFacts.jurisdiction == 'WV'`, do not attempt live games (EVONET unavailable)"*.
- **Shared navigation safety rules** (hoisted from each navigation intent so they live in ONE place that both `intent_navigate_to_game` and `intent_navigate_to_screen` inherit at the L0/L1 layer — see Design Decisions below):
  - "back to home" recovery anchor — `appium_mobile_press_key key="BACK"`, cap at 5 presses
  - loop detector — ≥5 same-screen visits in 20 actions → trip, SaveEvidence, terminate the intent
  - ≥1-verified-action-before-done — no `next=done` is honoured until at least one tap on a navigation control has been attempted in the intent window

**Requires**: 5-10 annotated screenshots from the operator + a written nav walkthrough.

### 2. `intent_navigate_to_game.md` tightening

Today the .md documents the fallback chain but lets the LLM short-circuit on `ResolveDirectory unresolved`. Changes:

- Add an explicit "**ResolveDirectory unresolved is the NORMAL case on a fresh DB. It does NOT mean the game is absent. Proceed to sub-strategy 1.**" rule near the top.
- Replace the ordered list with a checklist the agent visibly executes:
  1. Recents — tap the "Recently Played" strip if present.
  2. Category pill — read the kind→pill mapping from app_structure.md and tap.
  3. Search — tap search input, type the resolver query, tap first result.
  4. Scroll — swipe-scroll the grid up to N pages, tap tile when visible.
- Require **≥1 verified tap** on a navigation control before `next=done` is allowed. If after the chain no tap was attempted, the intent must `SaveEvidence(label=nav_no_attempts)` and emit done — explicit failure, not a hallucinated success.
- Update guardrails to name the right tool for back-out: `appium_mobile_press_key key="BACK"` (already done in C6 spec-005 patch).
- Document the "scroll" sub-strategy uses `appium_swipe` (or `appium_scroll` now whitelisted). The .md currently says "scroll" generically.

### 3. `intent_navigate_to_screen.md` tightening (general app nav)

Off-lobby navigation: getting to Settings, Account, Promotions, Rewards, Help. Or recovery: getting BACK to home from anywhere. Changes:

- Document **"back to home"** as the canonical recovery anchor — when lost or after a failed nav, return to home via either the Home bottom-nav item or N `appium_mobile_press_key key="BACK"` presses (cap at 5).
- Explicit anchor list — what `end_state_signatures` are legitimate targets (`home`, `settings`, `account`, `promotions`, `rewards`, `help`, plus any seeded ones).
- Cross-reference app_structure.md for screen locations.

### 4. Lobby-walk auto-discovery patches (2 lines)

- `_LOBBY_SCREEN_IDS` in [activities/observer_activity.py](../../activities/observer_activity.py) — add `home` (the casino app's actual lobby screen id, confirmed from T052 frontier data).
- `_TILE_ID_SUBSTRINGS` in [observers/screen_identity.py](../../observers/screen_identity.py) — add `casino game component tile`, `small_game_component`, `game_component`, `casino_game` (confirmed from T052 frontier data).

These are no-code-review-needed safety fixes — the patterns are taken directly from observed page-source content.

### 5. `extract_game_tiles` slug-collision fix

Today the tile slug comes from `rid.split("/")[-1] if "/" in rid else rid`. For Fanatics' generic id `casino game component tile`, every tile collides on the same slug — only the first survives. Fix: when the rid is a known generic pattern, build the slug from `_slugify(display_name)` instead.

### 6. CLAUDE.md update

Reflect:
- 8 intents (was 7 — intent_play_bonus stubbed during spec-005 prompt-stack push)
- Recent prompt-stack fixes (8 C/H items addressed)
- `app_structure.md` as the new L0-adjacent prompt layer
- Reference to this spec under "Recent Changes"

---

## Design decisions

### DD-001 — Keep `intent_navigate_to_game` and `intent_navigate_to_screen` as separate intents (not merged)

**Decision**: Both navigation intents stay separate; shared safety rules are hoisted into `app_structure.md` rather than duplicated in each intent body.

**Why not merge?**

| Dimension | `intent_navigate_to_screen` | `intent_navigate_to_game` |
|---|---|---|
| Input shape | A target signature (`settings`, `account`) — a known name | A `SessionIntent.target` with `kind` / `query` / `slug` — fuzzy, possibly unresolved |
| Target type | Logical screen identity (`screen_signatures`) | Game's `loaded_signature` (`game_directory`, may not exist yet) |
| Primary strategy | Directed screen-graph plan_path | Exploratory lobby walk (recents → category → search → scroll) |
| Source-of-truth table | `screen_transitions` / `screen_signatures` | `game_directory` / `game_playbook` |
| Failure semantic | "screen unreachable" (rare; usually a missing seed) | "game unresolved" (common on first run — fallback chain expected) |
| Side-effects we want | Plan-path traversal records new transitions | Lobby walk also triggers `game_directory` auto-discovery (T046) |
| Plan-graph role | Off-graph navigation (settings, account, recovery to home) | On-graph node that gates `load_context` → `play_game` |

Three structural reasons against merging:

1. **Picking the right intent gets simpler, not harder.** Separate intents give the LLM a closed-set enum of 8 with disjoint purposes. A merged `intent_navigate` would force per-turn introspection of the target arg to decide *"screen-walk or game-walk?"* — extra reasoning surface for no compositional benefit.
2. **The bodies don't fit in one 600-token budget.** `intent_navigate_to_game.md` already grows in this delivery (directive checklist, "unresolved ≠ absent" rule, ≥1-tap requirement, category-pill ref). `intent_navigate_to_screen.md` separately needs tightening (back-to-home, anchor list). Combined would breach the Constitution VI ≤600-token ceiling.
3. **The plan-graph wants different gates.** `graphs/casino_session.yaml` has `load_context` requiring `navigate_to_game.success` — semantically *"a game is now loaded"*, not *"we reached a screen"*. A single `intent_navigate` would leak domain logic into the plan-graph guard.

**What we do instead**: hoist the shared safety rules (back-to-home anchor, loop detector, destructive-button discipline, ≥1-action-before-done) into `app_structure.md` (see §1 of in-scope). Both intent bodies stay focused on their *unique* logic; both inherit the safety rules via the L0/L1 prompt prefix.

**Trigger to revisit**: if a third "navigate" intent is ever proposed (e.g. `intent_navigate_to_promotion`), we should look at this decision again. With three intents sharing 80% of their body, a generic `intent_navigate` with a sub-strategy dispatcher might pay for itself.

---

## Scope (out — defer to later deliveries)

| Item | Why deferred |
|---|---|
| `intent_play_game` refinement | Game-play reliability is delivery 007 |
| `intent_report` skipping `GenerateReport` | Workflow-level fix (workflow-side enforce GenerateReport call before terminating intent_report). Different surface. |
| `intent_play_bonus` body fill-out | US5 in spec-005 — stubbed for now |
| Per-game playbook seeding | Auto-populated on first play. No operator action required. |
| `scripts/seed_directory.py` | Auto-discovery (this delivery) makes manual seeding optional. |
| Persona dials wiring | Cleanup PR — non-blocking |
| Token-budget trimming on live_* kind files | Cleanup PR — non-blocking |
| Legacy `goals/slingo_qa_android/` removal | Cleanup PR — non-blocking |

---

## Success criteria

A `T052 blackjack` run on the test build must produce:

1. **≥1 `game_directory` row** auto-discovered from the lobby walk (was 0).
2. **At least one of {recents tap, category-pill tap, search-bar interaction, scroll-grid tap}** verified in the planner emission log during the `intent_navigate_to_game` window (was 0).
3. **`intent_navigate_to_game`** either:
   - **(success)** matches a `*_loaded` signature → `intent_load_game_context` fires next, OR
   - **(documented failure)** emits done with `SaveEvidence(label=nav_no_attempts)` *only after* ≥1 sub-strategy tap was attempted. No hallucinated "exhausted four strategies" rationale.
4. **`screen_transitions` gains ≥1 new edge** out of the lobby toward a category or game-loaded surface.
5. **No regression on auth** — `intent_authenticate` still completes within ±10% LLM calls vs the pre-change baseline.
6. **All 85 unit tests still pass** (`tests/contract`, `tests/integration`, `tests/workflowtests`).

---

## Task list (proposed)

| ID | Description | Effort | Blocked by |
|---|---|---|---|
| **T006-01** | Author `intent_navigate_to_game.md` rewrite — directive ordered checklist + "unresolved ≠ absent" rule + ≥1-tap requirement | S | — |
| **T006-02** | Apply the 2-line lobby-walk auto-discovery patches (`_LOBBY_SCREEN_IDS` + `_TILE_ID_SUBSTRINGS`) | XS | — |
| **T006-03** | `extract_game_tiles` slug-collision fix — fall back to `_slugify(display_name)` for generic rids | S | T006-02 |
| **T006-04** | Author `intent_navigate_to_screen.md` tightening — back-to-home recovery, anchor list, app_structure ref | S | — |
| **T006-05** | Author `prompts/persona/app_structure.md` (≤800 tokens) from the operator's screenshots + walkthrough | M | operator screenshots |
| **T006-06** | Update CLAUDE.md — 8-intent count, recent changes, app_structure reference | XS | T006-05 (after structure exists) |
| **T006-07** | Live validation: T052 blackjack rerun against success criteria 1-6. Diff vs baseline `bfee6b5d-...` | M | T006-01..06 |
| **T006-08** | Document outcome in `specs/006-app-navigation/results.md` (run id, success-criteria check, screenshots, follow-ups) | XS | T006-07 |

Effort: XS=≤30min, S=1-2h, M=half-day. Total ~1 day of focused work + operator-input time for T006-05.

---

## Sequencing

**Phase A (no operator input needed):** T006-01 → T006-02 → T006-03 → T006-04. Ship today. Rerun T052 to see partial improvement (auto-discovery should populate `game_directory`; intent rewrite should force fallback execution).

**Phase B (operator input):** Operator provides screenshots + walkthrough. T006-05 (app_structure.md) is written. T006-06 (CLAUDE.md) updated.

**Phase C (validation):** T006-07 full T052 rerun. T006-08 result doc. If success criteria pass → close 006 and open 007.

---

## Open questions

1. **Does the test-build account have a populated "Recently Played" strip?** If not, sub-strategy 1 of the chain is a no-op on T052 — relevant for grading the success criteria.
2. **Are there state-specific category pills?** (e.g. WV-only build hides "Live Dealer"). Affects the kind→pill map.
3. **Does the lobby have an "All Games" tab that obviates category navigation?** If so, sub-strategy 2 might be "scroll the All Games grid" instead.
4. **Should `intent_navigate_to_game` also handle the "deeplink" case** when SessionIntent comes with a slug that's already in the directory with a known `loaded_signature`? Today the .md says "use screen-graph plan_path", but this is untested. Worth a smoke pass before the broader chain runs.

---

## References

- Predecessor: [specs/005-casino-game-play-suite/](../005-casino-game-play-suite/) (tasks T037, T046, T052)
- Frontier evidence: T052 v9 run id `86fc0d35-b3c7-4ac6-b8dc-226d46185151` (2026-05-14)
- Tile-substring evidence: T052 v8 frontier rows (100 rows, screen_sig=`home`)
- FanCash Spins context (Daily Spin): [fancash_spins.md](../../fancash_spins.md)
- Game taxonomy + state availability: [games.md](../../games.md)
- Architecture rules: [.specify/memory/constitution.md](../../.specify/memory/constitution.md)
