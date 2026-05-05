# Implementation Plan: goal_slingo_qa

**Branch**: `001-goal-slingo-qa` | **Date**: 2026-03-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-goal-slingo-qa/spec.md`

## Summary

Add a new `AgentGoal` named `goal_slingo_qa` that uses mobile-mcp tools to play Slingo Cash Eruption on the Fanatics Casino Android app and report balance changes. The implementation adds 3 files (`goals/slingo_qa.py`, screen map JSONs) and edits 2 files (`goals/__init__.py`, `.env.example`). Zero changes to existing framework code (`AgentGoalWorkflow`, `ToolActivities`, `MCPClientManager`, `agent_prompt_generators.py`). The `get_mobile_mcp_server_definition()` in `shared/mcp_config.py` already exists.

## Technical Context

**Language/Version**: Python 3.10 (matches existing `.venv`)
**Primary Dependencies**: Temporal SDK, LiteLLM, FastAPI, `@anthropic/mobile-mcp@latest` (MCP server, launched via npx)
**Storage**: N/A (conversation history is in-memory within Temporal workflow state)
**Testing**: pytest (existing `tests/` directory)
**Target Platform**: macOS/Linux server running Temporal worker + Android emulator (emulator-5554, 1080x1920)
**Project Type**: AI agent goal definition (plugin to existing web-service)
**Performance Goals**: Full QA test (launch, navigate, play 5 spins, report) < 15 minutes; individual screenshot < 10 seconds
**Constraints**: Must not modify framework files; all device interaction via MCP tools only; LLM must handle WebView elements via vision (not accessibility tree)
**Scale/Scope**: 1 new goal file, 2 screen map JSON files, 2 file edits; ~500 lines of new code (mostly prompt text and coordinate data)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Same Architecture, New Goal | PASS | We add a new goal only. Zero changes to `AgentGoalWorkflow`, `ToolActivities`, `MCPClientManager`, or `agent_prompt_generators.py`. |
| II. Every Device Interaction Is an MCP Call | PASS | All 10 included tools are mobile-mcp tools. No direct ADB commands. |
| III. Screen Map Is Domain Knowledge in Prompt | PASS | Screen map JSONs are loaded into the goal `description` field. LLM references coordinates from prompt context. |
| IV. One Goal Per Test Scenario | PASS | Single goal `goal_slingo_qa` for the Slingo round test. |
| V. Adding a New Game = Adding a New Goal | PASS | This is exactly that pattern: new goal file + screen map + register in `__init__.py`. |
| VI. Human Approval at Financial Boundaries | PASS | Agent uses `next: "confirm"` for all tool calls. The goal description explicitly instructs the LLM to never buy extra spins and to use native exit instead. |

**Gate Result: PASS** - No violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-goal-slingo-qa/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal contracts only)
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
goals/
├── __init__.py              # EDIT - add slingo_qa import
└── slingo_qa.py             # NEW - goal definition

shared/
└── mcp_config.py            # EXISTS - get_mobile_mcp_server_definition() already present

screen_maps/
├── platform/
│   └── 1080x1920.json       # NEW - native app UI coordinates
└── games/
    └── slingo_cash_eruption/
        └── 1080x1920.json   # NEW - game-specific coordinates

the_game.md                  # EXISTS - game rules reference (content inlined into goal description)

# UNCHANGED:
workflows/agent_goal_workflow.py
activities/tool_activities.py
shared/mcp_client_manager.py
models/tool_definitions.py
prompts/agent_prompt_generators.py
api/main.py
frontend/
```

**Structure Decision**: This feature follows the existing goal-as-plugin pattern. New goals are Python files in `goals/` registered via `goals/__init__.py`. Screen maps are JSON files in `screen_maps/` keyed by resolution. No new directories, services, or abstractions needed.

## Complexity Tracking

> No violations to justify. Implementation follows existing patterns exactly.
