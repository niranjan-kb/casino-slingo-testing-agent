# Research: goal_slingo_qa

**Date**: 2026-03-12 | **Status**: Complete

## R1: MCP Server Package Name

**Decision**: Use `@anthropic/mobile-mcp@latest` (already in `shared/mcp_config.py`)
**Rationale**: The existing `get_mobile_mcp_server_definition()` function already uses this package. The spec referenced `@mobilenext/mobile-mcp@latest` but the codebase has `@anthropic/mobile-mcp@latest`. We follow the codebase.
**Alternatives considered**: `@mobilenext/mobile-mcp@latest` (spec draft) -- rejected because the existing implementation uses the `@anthropic` scoped package.

## R2: Goal Description Pattern

**Decision**: Inline all game rules, screen map coordinates, and QA instructions directly into the `description` field of `AgentGoal`
**Rationale**: The `description` field is injected into the LLM prompt as `Goal: {agent_goal.description}` (see `prompts/agent_prompt_generators.py:77`). The LLM uses this as its primary instruction set. Existing goals (food.py, travel.py) use inline strings. The description must be self-contained because the LLM has no file access.
**Alternatives considered**: Loading screen map JSON at runtime and injecting -- rejected for Phase 1 simplicity. The screen map JSONs exist as source-of-truth files but their content is inlined into the description string at code-write time. A future enhancement could load them dynamically.

## R3: Screen Map Coordinate Source

**Decision**: Use coordinates from `the_game.md` (1080x1920 FHD) as the primary screen map, cross-referenced with the Slingo Da Vinci Diamonds skill coordinates (1280x2856) for structural validation
**Rationale**: `the_game.md` provides coordinates calculated for 1080x1920 (standard Pixel 5 emulator). The Da Vinci skill uses 1280x2856 (different device). Since our target is `emulator-5554` at 1080x1920, we use `the_game.md` coordinates. The Da Vinci skill validates the structural approach (grid layout, reel positions, exit button pattern).
**Alternatives considered**: Using Da Vinci coordinates with scaling factor -- rejected because the games have different UI layouts (Da Vinci has different grid positioning than Cash Eruption).

## R4: WebView Element Interaction

**Decision**: All in-game elements must be tapped via `mobile_click_on_screen_at_coordinates` using known coordinates or vision-derived coordinates. `mobile_list_elements_on_screen` is only useful for native app screens (login, search, home, modals).
**Rationale**: Confirmed by the Da Vinci skill: "list_elements_on_screen cannot see any in-game elements." The game runs inside a WebView > iframe. The accessibility tree only exposes the native header (`close button`, `account button`, etc.) and any native modals ("Keep playing?" dialog). Everything inside the game iframe is rendered pixels only.
**Alternatives considered**: None -- this is a hard constraint of the WebView architecture.

## R5: END GAME Button Trap

**Decision**: Always exit via native header exit button (tap `close button` at header position) then tap "No thanks, exit" on the modal. Never tap the in-game END GAME button.
**Rationale**: Confirmed by the Da Vinci skill: "The SPIN FOR button's oversized touch area covers the END GAME area." The in-game END GAME button at (540, 1620) overlaps with the SPIN FOR button at (540, 1780). Tapping END GAME often triggers an extra spin purchase instead. The native exit button + modal is 100% reliable because it's a native Android view, not WebView.
**Alternatives considered**: Tapping END GAME with careful coordinate offset -- rejected because the touch target overlap is unpredictable.

## R6: Tool Call Pattern (MCP vs Native)

**Decision**: `tools=[]` (empty list) in the goal definition. All tools come from the MCP server dynamically.
**Rationale**: Looking at `workflow_helpers.py`, the workflow checks `is_mcp_tool()` to route tool execution. MCP tools are loaded dynamically at workflow start via `mcp_list_tools`. The `tools` list on `AgentGoal` is for native (non-MCP) tools only. Since all our tools come from mobile-mcp, the native tools list is empty. The tool definitions are populated from the MCP server's tool listing and appear in the prompt via `mcp_tools_info`.
**Alternatives considered**: Defining tool stubs in the `tools` list -- rejected because MCP tools are already described via `mcp_tools_info` in the prompt generator.

## R7: Typing Reliability

**Decision**: Use `mobile_type_keys` with the understanding it may drop characters. The goal description instructs the LLM to verify typed text via screenshot and retry if needed.
**Rationale**: The Da Vinci skill's `emulator-type` approach uses raw ADB `input keyevent` commands, which are not available as MCP tools. `mobile_type_keys` is the only MCP tool for text input. The existing skills note that both `adb shell input text` and `mobile_type_keys` drop characters. Mitigation: the goal description instructs screenshot-verify-retry.
**Alternatives considered**: Character-by-character typing via `mobile_press_button` -- rejected because `mobile_press_button` only supports BACK, HOME, VOLUME_UP, VOLUME_DOWN, ENTER (no character keys).

## R8: Example Conversation History Length

**Decision**: Include a concise but complete example showing: screenshot -> launch -> screenshot -> navigate -> play 1 spin -> end game -> report. Approximately 20-30 exchange turns.
**Rationale**: The food ordering goal example has ~40 exchanges and demonstrates the full flow including tool results. For mobile QA, the example needs to show the vision-based decision loop (screenshot -> analyze -> tap -> screenshot -> verify). The example should cover at least one wild handling scenario since that's the main decision point.
**Alternatives considered**: Minimal example (3-5 turns) -- rejected because the LLM needs to see the full screenshot -> action -> verify cycle to replicate it correctly.

## R9: Balance Reading Strategy

**Decision**: Read balance from screenshots using LLM vision. Before gameplay, read from native header (`cash balance label` via `list_elements_on_screen`). During/after gameplay, read from in-game bottom text bar ("Balance: $XX.XX" visible in screenshot).
**Rationale**: The native header balance is accessible via the accessibility tree before entering the game. Once inside the WebView, only the screenshot is available. The balance text is in the bottom-left corner of the game area with consistent styling (white text on black background).
**Alternatives considered**: Only using `list_elements_on_screen` -- rejected because it can't read in-game balance text.

## R10: Package Name by Environment

**Decision**: Default to `com.betfanatics.casino.dev` for the dev environment. Support parameterization via the goal description for other environments.
**Rationale**: Constitution specifies package path patterns: `com.betfanatics.casino` with `.dev`, `.test`, `.cert` suffixes (no suffix for prod). The Da Vinci skill confirms `com.betfanatics.casino.dev`. The goal description instructs the LLM to use the dev package name by default.
**Alternatives considered**: Environment variable for package name -- could be added later but not needed for Phase 1 since we target dev only.
