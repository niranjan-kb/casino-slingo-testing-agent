# Contract: LLM Response Schema

**Type**: Internal data contract
**Producer**: LLM (via `agent_toolPlanner` activity)
**Consumer**: `AgentGoalWorkflow.run()`

## Contract

The LLM MUST respond with JSON matching this schema for every turn:

```json
{
  "response": "<string - plain text message to display to user>",
  "next": "<'confirm' | 'question' | 'done'>",
  "tool": "<string - mobile-mcp tool name, or null>",
  "args": {
    "device": "emulator-5554",
    "<additional_args>": "<values>"
  }
}
```

### `next` Values for Slingo QA

| Value | When Used |
|-------|-----------|
| `"confirm"` | LLM has determined the next tool to call. Workflow waits for user confirmation (or auto-confirms). |
| `"question"` | LLM needs information from the user (e.g., credentials, which round to play). |
| `"done"` | All gameplay complete. `response` contains the final test report. |

### Tool Args by Tool

| Tool | Required Args |
|------|--------------|
| `mobile_take_screenshot` | `{ "device": "emulator-5554" }` |
| `mobile_click_on_screen_at_coordinates` | `{ "device": "emulator-5554", "x": <int>, "y": <int> }` |
| `mobile_swipe_on_screen` | `{ "device": "emulator-5554", "direction": "<up\|down\|left\|right>", "x": <int>, "y": <int>, "distance": <int> }` |
| `mobile_type_keys` | `{ "device": "emulator-5554", "text": "<string>", "submit": <bool> }` |
| `mobile_press_button` | `{ "device": "emulator-5554", "button": "<BACK\|HOME\|ENTER\|VOLUME_UP\|VOLUME_DOWN>" }` |
| `mobile_list_elements_on_screen` | `{ "device": "emulator-5554" }` |
| `mobile_launch_app` | `{ "device": "emulator-5554", "packageName": "<string>" }` |
| `mobile_get_screen_size` | `{ "device": "emulator-5554" }` |
| `mobile_save_screenshot` | `{ "device": "emulator-5554", "saveTo": "<string>" }` |
| `mobile_list_available_devices` | `{}` |

## Constraints

- `"pick-new-goal"` is NOT used in single-goal mode (this goal operates in single-goal mode)
- Every tool call MUST include `"device": "emulator-5554"` except `mobile_list_available_devices`
- The `response` field for `next: "done"` MUST contain a structured test report with balance before/after
