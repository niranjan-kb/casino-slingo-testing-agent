# Implementation Plan: Navigation Graph & Intent Layer

**Branch**: `004-nav-graph-intents` · **Date**: 2026-05-05 · **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-nav-graph-intents/spec.md`

## Summary

Replace per-task hand-coded goal procedures with a self-evolving screen-transition graph and a thin intent layer. The agent walks the graph deterministically when the map knows the way; the LLM is invoked only on novel screens; every successful action writes back to grow the map. A user prompt like *"play slingo till ±$100"* decomposes into intent sequence at runtime via the existing planner LLM call (closed-set intent enum on the same tool-use forcing schema that picks the next tool) — no hand-coded prompt parser, no per-prompt-shape branching code.

The technical approach is **additive**, not destructive: feature 003's observer framework ships first; 004 layers (a) auto-record contracts on existing tools (`SmartTap`, `VerifyTap`, `FindElementWithFallback`), (b) intent declarations as ≤600-token markdown files, (c) one new `signature_proposals` table for the unknown-screen → known-screen feedback loop, and (d) a workflow extension that exposes the active intent and session prompt as state. Existing tests + smoke flow continue to pass with no behavior regression.

## Technical Context

**Language/Version**: Python 3.10 (existing `.venv` via `uv`)
**Primary Dependencies**: `temporalio` (durable workflow spine), `litellm` → AWS Bedrock (`claude-sonnet-4-5`), `pyyaml`, MCP via SSE (`appium-mcp@1.56.3` PINNED per MCP-2), `appium-mcp` over `httpx` for SSE
**Storage**: SQLite (`data/screen_map.db`) as runtime source of truth (Principle I); Temporal workflow history for conversation + tool results; markdown files in `intents/` and `prompts/persona/` for declarative content
**Testing**: `pytest` with `--workflow-environment=time-skipping` for fast workflow tests; end-to-end smoke via `scripts/smoke_login.py --timeout 420`; new smoke script `scripts/smoke_play_intent.py` for Story 3
**Target Platform**: Android worker (live; native process per PT-2), iOS planned (PT-1), Web planned (PT-4). All workers communicate with Temporal at `localhost:7233` and appium-mcp at `localhost:3100/sse`.
**Project Type**: Python library + Temporal workers (single repo). No new frontend code; existing React UI consumes new `@workflow.query` handlers.
**Performance Goals**:
- Path-planner read query < 50 ms (in-memory BFS over ≤ 1k transitions)
- Per-screen overhead added by graph + intent layer: < 200 ms cached / < 1 s novel (SC-010)
- `goal_login` smoke (now `intent_authenticate` end-to-end): ≤ 420 s on test build (SC-001)
- After 3 verified runs, ≥ 80% of a flow's transitions are LLM-free (SC-002)
**Constraints**:
- Temporal workflow code must remain replay-deterministic (WF-1)
- `tool_activities.py` and `mcp_client_manager.py` are FROZEN (WF-3)
- `appium-mcp` PINNED to 1.56.3 (MCP-2)
- Intent declarations ≤ 600 tokens each (SC-012)
- No observer-side or auto-recorder failure may halt the goal loop (FR-027)
- All financial actions remain gated by `SHOW_CONFIRM` per Principle VII
**Scale/Scope**:
- 100–200 games per state (4 jurisdictions: NJ/PA/MI/WV)
- 4 v1 intents: `intent_authenticate`, `intent_navigate_to_screen`, `intent_play_game`, `intent_report`
- ~30 seeded login transitions today; expected to grow to ~200–500 across lobby + game flows in v1 + v2

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-evaluated after Phase 1 design.*

Evaluated against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v3.0.0 (2026-05-05).

### Principles

| Principle | Compliance | Notes |
|---|---|---|
| **I. Map primary, LLM fallback** | ✅ Direct implementation | Whole feature is this principle. |
| **II. One agent, intents at runtime** | ✅ Direct implementation | FR-013, FR-014, FR-015 codify exactly this. |
| **III. Observers side-channel, never halt** | ✅ Carries forward | FR-027 explicit; observer-pipeline unchanged from 003. |
| **IV. Self-healing non-negotiable** | ✅ Compatible | LLM fallback (FR-016) is the self-heal path for unknown screens; replanning on planner-divergence is built in (Story 1 scenario 3). |
| **V. Risk tiers gate confidence** | ✅ Compatible | Auto-record respects `should_verify_tap` per Story 2 scenario 3 + Assumption "Risk-tier policy is unchanged". |
| **VI. Operational soul only in prompts** | ✅ Direct enforcement | SC-012 forbids selectors/fallbacks/wait-tables in intent files; ≤ 600 tokens each. |
| **VII. Human approval at financial boundaries** | ✅ Unchanged | `intent_play_game` does not bypass `SHOW_CONFIRM`; bets/deposits remain gated. |

### Hard Rules

| Rule | Compliance | Notes |
|---|---|---|
| **PT-1..5** (platform topology) | ✅ Unchanged | No new worker hosts introduced. |
| **MCP-1..3** (MCP layer) | ✅ Unchanged | No new MCP servers; appium-mcp 1.56.3 retained. |
| **SC-1..3** (scalability) | ✅ Unchanged | Per-platform queues retained; state lives in Temporal + SQLite. |
| **WF-1** (replay determinism) | ✅ | All non-deterministic ops (DB writes, signature matching, LLM calls) live in activities. Workflow code adds state slots and query handlers only. |
| **WF-2** (state via queries) | ✅ | New state (`active_intent`, `session_prompt`, `completed_intents`) surfaces via three new `@workflow.query` handlers. No new signal types. |
| **WF-3** (frozen modules) | ✅ | Zero edits to `tool_activities.py`, `mcp_client_manager.py`. Intent dispatch lives in workflow code; auto-record helpers in `tools/slingo_qa/` (already non-frozen). |
| **MW-1** (transition writeback) | ✅ Direct implementation | FR-017, FR-018. |
| **MW-2** (element writeback) | ✅ Direct implementation | FR-019, FR-020. |
| **MW-3** (read-time decay) | ✅ Direct implementation | FR-024, FR-025, FR-026. |
| **MW-4** (signature proposals) | ✅ Direct implementation | FR-021, FR-022, FR-023. |

**Result**: ✅ **PASS — no violations, no Complexity Tracking entries needed.**

## Project Structure

### Documentation (this feature)

```
specs/004-nav-graph-intents/
├── plan.md              # this file
├── research.md          # Phase 0 — design questions resolved ← complete
├── data-model.md        # Phase 1 — entities + tables + workflow state ← complete
├── contracts/
│   ├── planner-llm.md           # extended plan_next_action schema ← complete
│   ├── intent-registry.md       # intent file format + registration ← complete
│   ├── auto-record.md           # SmartTap / VerifyTap / FEWFB writeback rules ← complete
│   ├── path-planner.md          # find_path / propose_next_step API ← complete
│   └── workflow-state.md        # new state slots + queries ← complete
├── quickstart.md        # Phase 1 — how to run a session under the new layer ← complete
├── checklists/
│   └── requirements.md  # already written by /speckit.specify
└── tasks.md             # Phase 2 — produced by /speckit.tasks (NOT this command)
```

### Source code (repository root)

```
intents/                           # NEW — closed-set intent registry
├── __init__.py                    # registry, loader, frontmatter parser
├── base.py                        # Intent dataclass + IntentDeclaration
├── authenticate.md                # ≤600 tokens — end-state, success check, guardrails
├── navigate_to_screen.md
├── play_game.md
└── report.md

tools/slingo_qa/                   # EXISTS — auto-record hooks added here
├── smart_tap.py                   # MODIFIED — call record_transition_observation
├── verify_tap.py                  # MODIFIED — emit (from, verb, target, to) tuple
├── find_element_with_fallback.py  # MODIFIED — call upsert_element on hit
└── ...                            # other tools unchanged

shared/
├── screen_map_db.py               # MODIFIED — add signature_proposals table + CRUD;
│                                  # add build_env/app_package columns where decay applies;
│                                  # apply read-time decay in get_transitions_from
├── screen_graph.py                # EXISTS — small change: read-time decay hook
└── ...

workflows/agent_goal_workflow.py   # MODIFIED — add active_intent, session_prompt,
                                   # completed_intents state; 3 new queries; intent
                                   # dispatch in the planner-result handler

activities/
├── tool_activities.py             # FROZEN per WF-3
├── observer_activity.py           # EXISTS (003)
└── intent_activity.py             # NEW — intent helpers (load registry, ranked games);
                                   # any non-deterministic intent ops

scripts/
├── smoke_login.py                 # EXISTS — still passes against intent_authenticate
├── smoke_play_intent.py           # NEW — Story 3 smoke: prompt → end-to-end
└── seed_login_transitions.py      # EXISTS (shipped with 003)

prompt_engine/
└── agent_prompt_generators.py     # MODIFIED — assemble active intent + map context
                                   # into the description per planner turn
```

**Structure Decision**: Single-repo Python project, no new top-level options. The intent registry lives at repo root in `intents/` for symmetry with `goals/`, `observers/`, and `tools/`. Auto-record changes are localized to existing tool modules (which are *not* frozen by WF-3); workflow extensions stay within `workflows/agent_goal_workflow.py`.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| _none_ | _n/a_ | _n/a_ |

---

## Post-Phase-1 Constitution Check

*Re-evaluation after data-model.md, contracts/, and quickstart.md are complete. Evaluated against constitution v3.0.0 (2026-05-05).*

### New design facts from Phase 1

| Artifact | Design decision | Constitution surface |
|---|---|---|
| `contracts/planner-llm.md` | `plan_next_action` schema extended with `active_intent` (closed-set enum per call) | WF-1, WF-3 |
| `contracts/workflow-state.md` | 3 new state slots + 3 `@workflow.query` handlers; planner-result handler patched in `agent_goal_workflow.py` | WF-1, WF-2 |
| `contracts/auto-record.md` | `SmartTap`, `VerifyTap`, `FindElementWithFallback` write back to DB on every verified action, wrapped in try/except | MW-1, MW-2, III |
| `contracts/path-planner.md` | `_effective_confidence` wrapper applies build-mismatch × 0.5 and linear staleness ramp at read time; stored confidence unchanged | MW-3 |
| `contracts/intent-registry.md` | Intent files ≤ 600 tokens, frontmatter only (no selectors/fallbacks) | VI, II |
| `data-model.md` | `signature_proposals` table added; `build_env`/`app_package` columns on 3 tables; `intent_activity.py` is a new (non-frozen) activity | MW-4, WF-3 |

### Principle re-check

| Principle | Post-design verdict | Notes |
|---|---|---|
| **I. Map primary, LLM fallback** | ✅ Strengthened | Path planner + auto-record make the map grow and stay current. Read-time decay (R5/R6) prevents stale high-confidence edges from bypassing LLM on new builds. |
| **II. One agent, intents at runtime** | ✅ Implemented in contracts | `planner-llm.md` encodes the closed-set per-turn enum. No branching code anywhere in the design. |
| **III. Observers never halt** | ✅ Unchanged | `contracts/auto-record.md` explicitly forbids raises; all three writeback hooks are try/except. |
| **IV. Self-healing** | ✅ Preserved | LLM fallback on planner-miss (FR-016) is the primary self-heal; `contracts/path-planner.md` documents the `None` return case that hands back to the LLM. |
| **V. Risk tiers** | ✅ Unchanged | `contracts/auto-record.md` confirms `should_verify_tap` graduation policy is not touched. |
| **VI. Operational soul in prompts only** | ✅ Enforced at design level | `contracts/intent-registry.md` enumerates what MUST NOT appear in intent bodies. ≤ 600-token limit encoded as startup validation. |
| **VII. Financial boundaries** | ✅ Unchanged | `intent_play_game` does not touch `SHOW_CONFIRM`; no financial-action contract changes. |

### Hard rule re-check (changed surfaces only)

| Rule | Post-design verdict | Notes |
|---|---|---|
| **WF-1** (replay determinism) | ✅ | All new state in `agent_goal_workflow.py` is written from activity return values or deterministic prompt constructs. No non-determinism in workflow code. |
| **WF-2** (state via queries) | ✅ | `contracts/workflow-state.md` adds exactly 3 `@workflow.query` handlers; no new signal types. |
| **WF-3** (frozen modules) | ⚠️ **Conditional pass** | `_build_plan_next_action_tool` in the frozen `tool_activities.py` needs a new optional parameter `allowed_intent_ids: List[str] = ()` to inject the closed-set enum. The function **body** is unchanged — only the schema dict it returns is extended. `ToolPromptInput` needs one new optional field. Implementation MUST use default values so no existing call sites break; the workflow passes the field; the activity's body logic is unmodified. If any call-site edit inside `tool_activities.py` beyond these two additions (default-value param, new `ToolPromptInput` field) is needed, **escalate to a design change** — do not break WF-3. |
| **MW-1..2** (writeback) | ✅ | `contracts/auto-record.md` maps both rules to concrete call sites in non-frozen tool files. |
| **MW-3** (read-time decay) | ✅ | `contracts/path-planner.md` documents `_effective_confidence` as read-only; stored confidence untouched. |
| **MW-4** (signature proposals) | ✅ | `data-model.md` defines the full `signature_proposals` schema, threshold rules (≥3 occurrences / ≥2 runs), and auto-promotion prohibition. |

### Result

✅ **PASS with one implementation note.** The design is constitution-compliant. The WF-3 conditional above is a **named implementation risk**: the minimal change to `tool_activities.py` (two default-value additions) is acceptable under WF-3's intent (preserve replay determinism and avoid logic churn in frozen modules), provided no logic inside the frozen functions changes. If that boundary cannot be held, the fallback is to inject `active_intent` constraint into `context_instructions` as prose rather than as a schema enum — weaker hallucination protection, acceptable for v1.
