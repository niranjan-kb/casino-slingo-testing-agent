# Data Model: goal_slingo_qa

**Date**: 2026-03-12 | **Status**: Complete

## Entities

### 1. AgentGoal: `goal_slingo_qa`

**Source**: `models/tool_definitions.py:AgentGoal` (existing dataclass, no modifications)

| Field | Type | Value | Notes |
|-------|------|-------|-------|
| `id` | `str` | `"goal_slingo_qa"` | Must match `AGENT_GOAL` env var |
| `category_tag` | `str` | `"casino-qa"` | New category; must be added to `GOAL_CATEGORIES` |
| `agent_name` | `str` | `"Slingo QA Agent"` | Displayed in UI header |
| `agent_friendly_description` | `str` | (see below) | Short description for goal picker |
| `tools` | `List[ToolDefinition]` | `[]` | Empty -- all tools come from MCP server |
| `description` | `str` | (see Goal Description section) | Full game rules + screen map + QA instructions |
| `starter_prompt` | `str` | (see below) | Initial greeting when goal loads |
| `example_conversation_history` | `str` | (see below) | Example tool call sequence |
| `mcp_server_definition` | `MCPServerDefinition` | (see below) | Points to mobile-mcp |

### 2. MCPServerDefinition: mobile-mcp

**Source**: `models/tool_definitions.py:MCPServerDefinition` (existing dataclass, no modifications)
**Factory**: `shared/mcp_config.py:get_mobile_mcp_server_definition()` (already exists)

| Field | Type | Value |
|-------|------|-------|
| `name` | `str` | `"mobile-mcp"` |
| `command` | `str` | `"npx"` |
| `args` | `List[str]` | `["-y", "@anthropic/mobile-mcp@latest"]` |
| `env` | `Optional[Dict]` | `None` |
| `connection_type` | `str` | `"stdio"` |
| `included_tools` | `List[str]` | (see Included Tools) |

**Included Tools** (10 tools):

| Tool Name | Purpose in Slingo QA |
|-----------|---------------------|
| `mobile_take_screenshot` | Read game state, balance, spin results |
| `mobile_click_on_screen_at_coordinates` | Tap spin button, grid numbers, exit button |
| `mobile_swipe_on_screen` | Scroll search results, navigate menus |
| `mobile_type_keys` | Type game name in search bar |
| `mobile_press_button` | Press BACK, HOME, ENTER |
| `mobile_list_elements_on_screen` | Read native UI (login, search, modals) |
| `mobile_launch_app` | Launch Fanatics Casino app |
| `mobile_get_screen_size` | Verify device resolution for screen map |
| `mobile_save_screenshot` | Archive test evidence to disk |
| `mobile_list_available_devices` | Verify emulator is connected |

### 3. Screen Map: Platform (1080x1920)

**Source**: `screen_maps/platform/1080x1920.json` (NEW file)
**Schema**: Follows constitution's Screen Map Schema

Key screens and elements:

| Screen | Element | x | y | Type |
|--------|---------|---|---|------|
| `home` | `search_bar` | 540 | 280 | input |
| `search_results` | `first_result` | 540 | 600 | button |
| `search_results` | `second_result` | 540 | 900 | button |
| `game_header` | `close_button` | 54 | 130 | button |
| `game_header` | `account_button` | 865 | 130 | button |
| `keep_playing_modal` | `keep_playing` | 540 | 1100 | button |
| `keep_playing_modal` | `no_thanks_exit` | 540 | 1300 | button |
| `fancash_prompt` | `start_playing` | 540 | 1400 | button |

### 4. Screen Map: Slingo Cash Eruption (1080x1920)

**Source**: `screen_maps/games/slingo_cash_eruption/1080x1920.json` (NEW file)
**Schema**: Follows constitution's Screen Map Schema

#### Grid Coordinates (5x5)

| | Col 1 (x=220) | Col 2 (x=380) | Col 3 (x=540) | Col 4 (x=700) | Col 5 (x=860) |
|---|---|---|---|---|---|
| Row 1 (y=730) | (220,730) | (380,730) | (540,730) | (700,730) | (860,730) |
| Row 2 (y=890) | (220,890) | (380,890) | (540,890) | (700,890) | (860,890) |
| Row 3 (y=1050) | (220,1050) | (380,1050) | (540,1050) | (700,1050) | (860,1050) |
| Row 4 (y=1210) | (220,1210) | (380,1210) | (540,1210) | (700,1210) | (860,1210) |
| Row 5 (y=1370) | (220,1370) | (380,1370) | (540,1370) | (700,1370) | (860,1370) |

#### Reel Slots (1x5)

| Slot | x | y |
|------|---|---|
| Slot 1 | 220 | 1550 |
| Slot 2 | 380 | 1550 |
| Slot 3 | 540 | 1550 |
| Slot 4 | 700 | 1550 |
| Slot 5 | 860 | 1550 |

#### Controls

| Element | x | y | Intent |
|---------|---|---|--------|
| `spin_button` | 540 | 1780 | Start spin / buy extra spin |
| `end_game_button` | 540 | 1620 | DO NOT TAP (touch target overlap) |
| `stake_adjuster` | 220 | 1780 | Open bet menu |
| `settings_button` | 860 | 1780 | Game settings |
| `game_over_dismiss` | 540 | 1050 | Dismiss Game Over modal |

### 5. Test Report (LLM Output)

Not a code entity. This is the structured text the LLM produces as its final `response` field when `next: "done"`. Format defined in the goal description and example conversation history.

Fields: starting_balance, ending_balance, balance_delta, spins_played, wilds_encountered, super_wilds_encountered, extra_spins_purchased (always 0), status (PASS/FAIL), anomalies.

## State Transitions

### Game State Machine (encoded in goal description)

```
[APP_CLOSED] --launch_app--> [HOME_SCREEN]
[HOME_SCREEN] --tap_search--> [SEARCH_SCREEN]
[SEARCH_SCREEN] --type+search--> [SEARCH_RESULTS]
[SEARCH_RESULTS] --tap_game--> [FANCASH_PROMPT] or [GAME_LOADING]
[FANCASH_PROMPT] --tap_start--> [GAME_LOADING]
[GAME_LOADING] --wait--> [TUTORIAL] or [GAME_READY]
[TUTORIAL] --tap_play_x4--> [GAME_READY]
[GAME_READY] --tap_spin--> [SPINNING]
[SPINNING] --animation_done--> [SPIN_RESULT]
[SPIN_RESULT] --wild_detected--> [WILD_SELECT]
[SPIN_RESULT] --no_wild,spins>0--> [GAME_READY]
[SPIN_RESULT] --no_wild,spins=0--> [EXTRA_SPINS_PHASE]
[WILD_SELECT] --tap_number--> [SPIN_RESULT]
[EXTRA_SPINS_PHASE] --native_exit--> [KEEP_PLAYING_MODAL]
[KEEP_PLAYING_MODAL] --no_thanks--> [SEARCH_RESULTS]
[SEARCH_RESULTS] --read_balance--> [REPORT]
```

## Validation Rules

| Rule | Where Enforced |
|------|---------------|
| `id` must match `AGENT_GOAL` env var | `goals/__init__.py` lookup |
| `category_tag` must be in `GOAL_CATEGORIES` | `goals/__init__.py` filtering |
| `included_tools` must be valid mobile-mcp tool names | MCP server returns error for unknown tools |
| Screen map coordinates must match device resolution | `mobile_get_screen_size` verification step in goal description |
| Extra spins must never be purchased | Goal description instructs native exit; no `SPIN FOR` tap |
| Balance must be read before AND after gameplay | Goal description mandates pre/post balance screenshots |
