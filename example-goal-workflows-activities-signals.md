# Casino Slingo QA: How It Maps to the Existing Agent Architecture

## The Existing Agent Loop (unchanged)

This is `AgentGoalWorkflow.run()` -- we do NOT modify this. We just plug in a new goal.

```
                         AgentGoalWorkflow
                         =================

   +---------------------------------------------------------+
   |                                                         |
   |  1. WAIT for signal (user_prompt / confirm / end)       |
   |     |                                                   |
   |     v                                                   |
   |  2. If prompt: validate -> send to LLM                  |
   |     |          (agent_toolPlanner activity)              |
   |     |                                                   |
   |     v                                                   |
   |  3. LLM responds with JSON:                             |
   |     {                                                   |
   |       "response": "I see the home screen...",           |
   |       "next": "confirm",                                |
   |       "tool": "mobile_take_screenshot",                      |
   |       "args": {}                                        |
   |     }                                                   |
   |     |                                                   |
   |     v                                                   |
   |  4. If next=confirm: wait for user confirm signal       |
   |     (or auto-confirm if SHOW_CONFIRM=False)             |
   |     |                                                   |
   |     v                                                   |
   |  5. Execute tool as activity                            |
   |     (mcp_tool_activity -> mobile-mcp server)            |
   |     |                                                   |
   |     v                                                   |
   |  6. Tool result -> conversation history                 |
   |     |                                                   |
   |     v                                                   |
   |  7. LLM sees result -> decides next tool -> LOOP        |
   |     |                                                   |
   |     v                                                   |
   |  8. When done: next="done", return report               |
   |                                                         |
   +---------------------------------------------------------+
```

## mobile-mcp Tool Reference (Actual Tool Names + Args)

These are the real tools from `@mobilenext/mobile-mcp`. Every tool requires a `device` arg.

### Core Tools the LLM Will Use

```
TOOL: mobile_take_screenshot
ARGS: { "device": "emulator-5554" }
RETURNS: { "content": [{ "type": "image", "data": "<base64>", "mimeType": "image/jpeg" }] }
NOTE: Returns actual image. LLM sees it visually.

TOOL: mobile_click_on_screen_at_coordinates
ARGS: { "device": "emulator-5554", "x": 540, "y": 1780 }
RETURNS: { "content": [{ "type": "text", "text": "Clicked on screen at coordinates: 540, 1780" }] }

TOOL: mobile_swipe_on_screen
ARGS: { "device": "emulator-5554", "direction": "up", "x": 540, "y": 960, "distance": 400 }
RETURNS: { "content": [{ "type": "text", "text": "Swiped up 400 pixels from coordinates: 540, 960" }] }

TOOL: mobile_type_keys
ARGS: { "device": "emulator-5554", "text": "Slingo", "submit": true }
RETURNS: { "content": [{ "type": "text", "text": "Typed text: Slingo" }] }

TOOL: mobile_press_button
ARGS: { "device": "emulator-5554", "button": "BACK" }
RETURNS: { "content": [{ "type": "text", "text": "Pressed the button: BACK" }] }
NOTE: Supported buttons: BACK, HOME, VOLUME_UP, VOLUME_DOWN, ENTER

TOOL: mobile_list_elements_on_screen
ARGS: { "device": "emulator-5554" }
RETURNS: { "content": [{ "type": "text", "text": "Found these elements on screen: [...]" }] }
NOTE: Returns accessibility tree with coordinates. Useful for non-game screens (login, search).
      Game screens (WebView/iframe) likely return NO elements -- use screenshot + vision instead.

TOOL: mobile_launch_app
ARGS: { "device": "emulator-5554", "packageName": "com.betfanatics.casino" }
RETURNS: { "content": [{ "type": "text", "text": "Launched app com.betfanatics.casino" }] }

TOOL: mobile_list_available_devices
ARGS: {}
RETURNS: { "content": [{ "type": "text", "text": "{\"devices\":[{\"id\":\"emulator-5554\",\"name\":\"Pixel_5\",\"platform\":\"android\",...}]}" }] }
```

### Additional Useful Tools

```
TOOL: mobile_get_screen_size
ARGS: { "device": "emulator-5554" }
RETURNS: "Screen size is 1080x1920 pixels"
NOTE: Critical for screen map resolution keying.

TOOL: mobile_save_screenshot
ARGS: { "device": "emulator-5554", "saveTo": "/tmp/screenshots/spin_1.png" }
RETURNS: "Screenshot saved to: /tmp/screenshots/spin_1.png"
NOTE: For archiving test evidence.

TOOL: mobile_long_press_on_screen_at_coordinates
ARGS: { "device": "emulator-5554", "x": 540, "y": 1050, "duration": 1000 }
RETURNS: "Long pressed on screen at coordinates: 540, 1050 for 1000ms"

TOOL: mobile_install_app
ARGS: { "device": "emulator-5554", "path": "/tmp/fanatics-casino-8.3.0.apk" }
RETURNS: "Installed app from /tmp/fanatics-casino-8.3.0.apk"
NOTE: For new build testing workflow.

TOOL: mobile_terminate_app
ARGS: { "device": "emulator-5554", "packageName": "com.betfanatics.casino" }
RETURNS: "Terminated app com.betfanatics.casino"
```

## What We Add (goal + MCP server config only)

### New Goal: `goal_slingo_qa`

```python
# goals/slingo_qa.py

goal_slingo_qa = AgentGoal(
    id="goal_slingo_qa",
    category_tag="casino-qa",
    agent_name="Slingo QA Agent",
    agent_friendly_description="Play Slingo Cash Eruption and report results",
    tools=[],  # populated dynamically from mobile-mcp at workflow start
    mcp_server_definition=get_mobile_mcp_server_definition(
        included_tools=[
            "mobile_take_screenshot",
            "mobile_click_on_screen_at_coordinates",
            "mobile_swipe_on_screen",
            "mobile_type_keys",
            "mobile_press_button",
            "mobile_list_elements_on_screen",
            "mobile_launch_app",
            "mobile_get_screen_size",
            "mobile_save_screenshot",
            "mobile_list_available_devices",
        ]
    ),
    description="""...(game rules, screen map, QA instructions)...""",
    starter_prompt="Starting Slingo Cash Eruption QA test...",
    example_conversation_history="...(example tool call sequence)...",
)
```

### New MCP Server: mobile-mcp

```python
# shared/mcp_config.py

def get_mobile_mcp_server_definition(included_tools: list[str]) -> MCPServerDefinition:
    return MCPServerDefinition(
        name="mobile-mcp",
        command="npx",
        args=["-y", "@mobilenext/mobile-mcp@latest"],
        env=None,
        included_tools=included_tools,
    )
```

## Concrete Example: One Spin Cycle

This shows the actual signal/activity flow for a single spin in Slingo:

```
Frontend (React)       API (FastAPI)       Temporal Workflow         Activities            mobile-mcp
================       ============       ================         ==========            ==========
     |                      |                    |                      |                      |
     | POST /start          |                    |                      |                      |
     |--------------------->| start_workflow()   |                      |                      |
     |                      |------------------->|                      |                      |
     |                      |                    | load_mcp_tools()     |                      |
     |                      |                    |--------------------->| mcp_list_tools       |
     |                      |                    |                      |--------------------->|
     |                      |                    |                      |<-- tools list -------|
     |                      |                    |<-- tools registered -|                      |
     |                      |                    |                      |                      |
     |                      |                    | wait for signal...   |                      |
     |                      |                    |                      |                      |
     | POST /send-prompt    |                    |                      |                      |
     | "Start the QA test"  | signal:user_prompt |                      |                      |
     |--------------------->|------------------->|                      |                      |
     |                      |                    |                      |                      |
     |                      |                    | validate prompt      |                      |
     |                      |                    |--------------------->| agent_validatePrompt |
     |                      |                    |<-- valid ------------|                      |
     |                      |                    |                      |                      |
     |                      |                    | generate prompt      |                      |
     |                      |                    | (goal description    |                      |
     |                      |                    |  + tools + history)  |                      |
     |                      |                    |--------------------->| agent_toolPlanner    |
     |                      |                    |                      | (LLM decides:        |
     |                      |                    |                      |  "I need to see the  |
     |                      |                    |                      |   screen first")     |
     |                      |                    |<--------------------|                      |
     |                      |                    |                      |                      |
     |                      |                    | LLM returned:        |                      |
     |                      |                    | {                    |                      |
     |                      |                    |   "next": "confirm", |                      |
     |                      |                    |   "tool":            |                      |
     |                      |                    |   "mobile_take_screenshot"|                      |
     |                      |                    |   "args": {}         |                      |
     |                      |                    | }                    |                      |
     |                      |                    |                      |                      |
     | query: tool_data     |                    |                      |                      |
     |<- show confirm btn --|                    |                      |                      |
     |                      |                    |                      |                      |
     | POST /confirm        | signal: confirm    |                      |                      |
     |--------------------->|------------------->|                      |                      |
     |                      |                    |                      |                      |
     |                      |                    | execute_tool         |                      |
     |                      |                    |--------------------->| mcp_tool_activity    |
     |                      |                    |                      | "mobile_take_screenshot"  |
     |                      |                    |                      |--------------------->|
     |                      |                    |                      |<-- base64 image -----|
     |                      |                    |<-- screenshot result |                      |
     |                      |                    |                      |                      |
     |                      |                    | result -> history    |                      |
     |                      |                    | auto-prompt LLM      |                      |
     |                      |                    |  with tool result    |                      |
     |                      |                    |--------------------->| agent_toolPlanner    |
     |                      |                    |                      | (LLM sees screenshot,|
     |                      |                    |                      |  reads balance $50,  |
     |                      |                    |                      |  sees spin button)   |
     |                      |                    |<--------------------|                      |
     |                      |                    |                      |                      |
     |                      |                    | LLM returned:        |                      |
     |                      |                    | {                    |                      |
     |                      |                    |   "next": "confirm", |                      |
     |                      |                    |   "tool":            |                      |
     |                      |                    |    "mobile_click_on_screen_at_coordinates",     |                      |
     |                      |                    |   "args": {          |                      |
     |                      |                    |     "x": 540,        |                      |
     |                      |                    |     "y": 1780        |                      |
     |                      |                    |   }                  |                      |
     |                      |                    | }                    |                      |
     |                      |                    |                      |                      |
     | (confirm or auto)    |                    |                      |                      |
     |--------------------->|------------------->|                      |                      |
     |                      |                    |--------------------->| mcp_tool_activity    |
     |                      |                    |                      | "mobile_click_on_screen_at_coordinates"         |
     |                      |                    |                      | {x:540, y:1780}      |
     |                      |                    |                      |--------------------->|
     |                      |                    |                      |<-- tap success ------|
     |                      |                    |<-- result -----------|                      |
     |                      |                    |                      |                      |
     |                      |                    | LOOP CONTINUES:      |                      |
     |                      |                    |  screenshot ->       |                      |
     |                      |                    |  see spin result ->  |                      |
     |                      |                    |  handle wilds ->     |                      |
     |                      |                    |  tap spin again ->   |                      |
     |                      |                    |  ... x5 spins ...    |                      |
     |                      |                    |  end game ->         |                      |
     |                      |                    |  read final balance  |                      |
     |                      |                    |  next="done"         |                      |
     |                      |                    |                      |                      |
     | query: history       |                    |                      |                      |
     |<- full test report --|                    |                      |                      |
```

## What Changes vs Existing Architecture

| Component | Change | Details |
|-----------|--------|---------|
| `AgentGoalWorkflow` | NONE | Unchanged. Exact same loop. |
| `ToolActivities` | NONE | `mcp_tool_activity` already handles MCP tools. |
| `MCPClientManager` | NONE | Already pools MCP connections. |
| `goals/__init__.py` | ADD import | `from goals.slingo_qa import slingo_qa_goals` |
| `goals/slingo_qa.py` | NEW | Goal definition with game rules in description |
| `shared/mcp_config.py` | ADD function | `get_mobile_mcp_server_definition()` |
| `.env` | ADD vars | `AGENT_GOAL=goal_slingo_qa`, `ANDROID_SERIAL`, `VISION_LLM_MODEL` |
| Frontend | NONE* | Chat UI already shows tool calls + confirm buttons |

*Frontend may need minor updates to render screenshots inline from MCP results.

## The Key Insight

The LLM is the brain. It decides every action. The goal description + screen map data
in the prompt give it the domain knowledge to make good decisions. mobile-mcp tools
are just tools like any other -- screenshot, tap, swipe, type_text, press_button.

The existing agent loop handles everything:
- LLM decides next tool -> existing
- User confirms -> existing (signals)
- Tool executes via MCP -> existing (mcp_tool_activity)
- Result feeds back to LLM -> existing (conversation history)
- LLM decides next tool -> loop

We are NOT building new workflows. We are adding a new GOAL that uses mobile-mcp
tools instead of Stripe/flight/HR tools. Same architecture. Different tools.

## .env Configuration

```env
# Change this one line to switch the agent to casino QA mode
AGENT_GOAL=goal_slingo_qa

# Add these for mobile-mcp
ANDROID_SERIAL=emulator-5554

# Vision LLM (for screenshot analysis -- may want a different model)
VISION_LLM_MODEL=anthropic/claude-sonnet-4-20250514
VISION_LLM_KEY=sk-ant-...

# Existing (unchanged)
LLM_MODEL=openai/gpt-4o
LLM_KEY=sk-proj-...
SHOW_CONFIRM=True
GOAL_CATEGORIES=casino-qa
```
