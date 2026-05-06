# Specification Quality Checklist: Navigation Graph & Intent Layer

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-05
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

### Validation review (2026-05-05)

- **Content Quality**: PASS. Spec describes the navigation graph and intent layer in terms of capability, end-states, and persona-level outcomes. Some terminology unavoidably names the existing schema (`screen_transitions`, `screen_elements`, `screen_signatures`, `game_catalog`) because those tables exist today as the substrate this feature builds on; that's domain vocabulary, not implementation leak.
- **Requirement Completeness**: PASS. 27 functional requirements grouped by lifecycle phase (write contract, read contract, game catalog, intent layer, auto-record contracts, unknown-screen proposal, confidence decay, run continuity). All testable. Edge cases cover branching transitions, loops, empty page-source, multi-game catalog matches, build-removed screens, missing intent labels, planner-returns-None, and intent conflicts.
- **Feature Readiness**: PASS. Each P1 user story (login as graph traversal, tap-and-verify writeback, prompt decomposition into intents) is independently testable and forms a viable MVP. P2 stories (game catalog by name, signature proposals, element auto-record) compound the MVP value. P3 (confidence decay) is honestly scoped as deferrable.

### Dependency on Feature 003

This feature explicitly depends on Feature 003 (Observer Framework):

- `obs.unknown_screen` is the producer for FR-021's signature-proposal flow.
- `observation_log` is the persistence substrate that feeds the proposal threshold.
- FR-027's run-continuity invariant carries over verbatim.

Feature 003 has shipped on branch `003-observer-framework` and is awaiting PR review. This feature's branch is `004-nav-graph-intents`.

### Surface dependencies on existing committed code

- `screen_transitions` table + CRUD methods landed in 003's commit. This spec's FR-001..FR-007 build on those.
- `game_catalog` table + CRUD methods landed in 003's commit. This spec's FR-008..FR-011 build on those.
- `shared/screen_graph.py` (max-min-confidence path planner) landed in 003's commit. This spec's FR-005..FR-007 are a contract over that module.
- `scripts/seed_login_transitions.py` landed in 003's commit. This spec's User Story 1 verifies that seeded data drives the new intent layer.

No [NEEDS CLARIFICATION] markers; the proposed scope was discussed in design conversation and surfaces are well-known. Ready for `/speckit.plan` when the user is ready.

### Update 2026-05-05 — closed the prompt-decomposition ambiguity

Original FR-014/-015 left a load-bearing ambiguity: FR-014 said "no hand-coded goal selector" while FR-015 named a specific prompt shape (`"play <game> till ±$<budget>"`). Two readings: (A) regex-parse the named shape — the trap; (B) LLM-driven continuous intent inference — the design intent. Tightenings applied:

- **FR-014** rewritten to make continuous inference explicit: the SAME planner LLM call that picks the next tool also picks the active intent, every turn, from the closed-set intent registry. No hand-coded prompt parser, regex shape match, or per-prompt-shape branching code path is permitted. The LLM may switch the active intent on any turn.
- **FR-015** rewritten to drop the hardcoded shape: any natural-language session prompt drives the run; new prompt shapes MUST NOT require code changes.
- **Story 3 acceptance scenarios** rewritten to match (no longer reference a specific regex shape; new scenario 4 verifies a novel-prompt-shape works without code changes).
- **SC-011** added: a previously-unseen prompt shape MUST drive a coherent intent sequence to a terminal state without code changes.
- **SC-012** added: 0 intent declarations contain selectors, fallback candidates, wait-time tables, or per-prompt-shape branching; intent files are end-state declarations only.
- **Out-of-scope** updated: removed "Fully natural-language prompt parsing beyond a small set of high-level shapes" (that was the contradicting bullet); replaced with "Voice / spoken-prompt input" as the actual NL boundary.

Total: 27 FRs, 12 SCs, 7 user stories (3 P1, 3 P2, 1 P3). All checklist items still pass; spec is internally consistent.
