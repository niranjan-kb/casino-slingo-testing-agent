# Implementation Prompt

Implement `goal_slingo_qa` by following `specs/001-goal-slingo-qa/tasks.md` in order (T001-T023).

## Key Context

- **Pattern**: Follow `goals/food.py` as the reference for goal structure, description style, and example_conversation_history format
- **MCP config**: `get_mobile_mcp_server_definition()` already exists in `shared/mcp_config.py` -- just import and call it
- **Tools list**: `tools=[]` (empty) -- all 10 tools come from mobile-mcp dynamically
- **Game rules**: Inline content from `the_game.md` into the description string
- **Screen coordinates**: Inline from `screen_maps/` JSONs (source: `the_game.md` 1080x1920 values)
- **Credentials**: Inject via f-string: `f"Test email: {os.getenv('TEST_EMAIL', 'not configured')}"`
- **No framework changes**: Do NOT modify `agent_goal_workflow.py`, `tool_activities.py`, `mcp_client_manager.py`, or `agent_prompt_generators.py`

## Critical Domain Knowledge for the Description

1. **WebView blindness**: `mobile_list_elements_on_screen` cannot see in-game elements -- only native header/modals. All game taps use coordinates.
2. **END GAME trap**: Never tap in-game END GAME (540, 1620) -- touch target overlaps SPIN FOR. Always exit via native header close button then "No thanks, exit" modal.
3. **Typing drops chars**: `mobile_type_keys` is unreliable. Instruct LLM to screenshot-verify-retry after typing.
4. **5 base spins** (not 10). Default stake $0.20.

## Read These Files

- `specs/001-goal-slingo-qa/tasks.md` -- task checklist
- `specs/001-goal-slingo-qa/data-model.md` -- entities, coordinates, state machine
- `specs/001-goal-slingo-qa/research.md` -- 10 design decisions
- `goals/food.py` -- reference pattern for goal structure
- `the_game.md` -- game rules to inline
- `shared/mcp_config.py` -- existing MCP factory
- `goals/__init__.py` -- where to register
