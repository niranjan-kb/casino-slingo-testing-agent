---
name: mobile-goal-dev
description: Author, register, and verify a new platform-agnostic capability goal (e.g. goal_login, goal_play_slingo, goal_place_bet) for the Casino QA agent. Use when the user says "add a goal", "create a new goal", "wire up goal_X", "extract this flow as a goal", or anything about composing the agent's capability surface. Walks through prompt scaffolding, registration in goals/__init__.py, and a smoke-run.
---

# mobile-goal-dev — Build a new agent capability-goal

You are helping author a new **goal** for the Casino QA agent. The agent has **one persona, many goals**: it composes capability-goals at runtime under a single soul/identity. Each goal is a self-contained capability the agent can dispatch to.

## Architectural rules (non-negotiable)

1. **Goals are platform-agnostic.** Name them for what they do (`goal_login`, `goal_play_slingo`, `goal_place_bet`), never for the platform (`goal_login_android` ❌). Platform/build/resolution differences live in the screen-map DB.
2. **Persona is shared.** Every goal loads `prompts/persona/soul.md` + `prompts/persona/identity.md` via `prompts.persona.soul_and_identity()`. Goals only contribute their own `user.md` + `tools.md`.
3. **Self-healing is mandatory.** A goal must NEVER set `next='question'` for routine recovery — only for sanctioned questions (e.g. `ASK-USER-OTP` in cert/prod). Tool errors → try another strategy → page-source dump → coordinate fallback. Save evidence and continue rather than halt.
4. **Determinism first, LLM as fallback.** When the screen-map has a high-confidence intent, use it without LLM. LLM is for novelty.
5. **Every successful action updates the screen-map.** Free data, never waste it.

## Recipe — author a new goal

### 1. Scaffold the directory

```bash
mkdir -p goals/<goal_id>/prompts
```

### 2. Write `goals/<goal_id>/prompts/user.md`

This is the only **required** prompt file (tools.md is optional; reuse goal_login's if your tool surface is the same). The user.md contains the phase logic — what the agent does to fulfill the capability.

Required structure:

```markdown
# <goal_id> — <one-line description>

Your job: <single sentence describing the capability and where it stops>.

## Live env values (injected per run)

- `BUILD_ENV` = `{{BUILD_ENV}}`
- (other env vars used in this goal — only list what you actually reference)

## Phases (run in order, stop on first failure that exhausts recovery)

### Phase 0 — <prerequisite, e.g. device + session>

1. <numbered steps>

### Phase 1 — <next phase>

(repeat)

### Phase N — Confirm + report

1. Verify the success indicator (a screen anchor or DB state change).
2. Respond `next='done'` with `<GOAL_ID> PASS — <key=value summary>`.

## Self-healing reminders (from soul)
- (3-5 bullets specific to this goal — common failure modes and recovery)
```

Tips:
- Reference selectors as concrete xpath / resource-id values you've **verified on a real run**. No guessing.
- Use placeholders `{{BUILD_ENV}}`, `{{TEST_EMAIL}}`, etc. — they're injected by `prompts.persona.env_context()`. Add new ones to `env_context()` if needed.
- Keep phases small (≤ ~10 steps each). Big phases mean the LLM has to keep too much in context.

### 3. Write `goals/<goal_id>/prompt_loader.py`

Copy from `goals/login/prompt_loader.py`. Three functions:

```python
def assemble_description() -> str:
    # Soul + identity (shared) + tools.md + user.md (this goal's)
def build_starter_prompt() -> str:
    # 4-6 lines greeting + env summary + how to invoke
def build_example_conversation() -> str:
    # Few-shot example showing the agent's voice on this goal
```

### 4. Write `goals/<goal_id>/__init__.py`

```python
from goals.<goal_id>.prompt_loader import (
    assemble_description, build_example_conversation, build_starter_prompt,
)
from models.tool_definitions import AgentGoal
from shared.mcp_config import get_appium_mcp_server_definition
from tools.tool_registry import (
    # only the local tools this goal needs
    ...
)

_APPIUM_TOOLS = [
    # only the appium-mcp tools this goal needs (subset is good — fewer = clearer LLM)
    "appium_screenshot", "appium_click", "appium_set_value", "appium_get_text",
    "appium_find_element", "appium_get_page_source", "appium_app",
    "create_session", "delete_session", "select_device",
    # add per-goal: appium_swipe (game), appium_alert, etc.
]

_LOCAL_TOOLS = [
    # SmartTap, WaitSeconds, TapCoordinate, DetectScreen, LookupCoords, VerifyTap, SaveEvidence
    # Plus GenerateReport ONLY if this goal owns the final QA report
]

goal_<goal_id> = AgentGoal(
    id="goal_<goal_id>",
    category_tag="casino-qa",
    agent_name="<Display name>",
    agent_friendly_description="<One-paragraph description of the capability>",
    tools=list(_LOCAL_TOOLS),
    mcp_server_definition=get_appium_mcp_server_definition(
        platform="android",
        included_tools=_APPIUM_TOOLS,
    ),
    description=assemble_description(),
    starter_prompt=build_starter_prompt(),
    example_conversation_history=build_example_conversation(),
)

<goal_id>_goals = [goal_<goal_id>]
```

### 5. Register in `goals/__init__.py`

```python
from goals.<goal_id> import <goal_id>_goals
# ...
goal_list.extend(<goal_id>_goals)
```

### 6. Smoke-run

```bash
# 1. Validate the goal renders without errors:
set -a && source .env && set +a
uv run python -c "from goals.<goal_id> import goal_<goal_id>; print(goal_<goal_id>.starter_prompt)"

# 2. Rebuild the API (the goal is baked into the workflow input at start time):
docker compose -f docker-compose.yml build api
docker compose -f docker-compose.yml up -d api

# 3. Restart the worker if you changed Python code (tools/, activities/):
pkill -f run_worker_android.py
PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py > /tmp/android-worker.log 2>&1 &

# 4. Aim the workflow at this goal:
#    Either set AGENT_GOAL=goal_<goal_id> in .env and rebuild api,
#    or use the multi-goal picker (AGENT_GOAL=goal_choose_agent_type).

# 5. Run it end-to-end:
curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=<your-trigger-phrase>'
tail -F /tmp/android-worker.log | grep -E 'next_step|Raw LLM response|FAILED|<GOAL_ID> PASS'
```

## Common gotchas

- **`appium_click` requires `elementUUID`** (not `elementId`).
- **`appium_set_value` requires `text`** (not `value`).
- **`appium_find_element` requires BOTH `strategy` AND `selector`.**
- Numeric strings (OTP, codes) must stay strings — `_convert_args_types` in `activities/tool_activities.py` preserves string-only keys (`text`, `selector`, `strategy`, `elementUUID`, `id`, `key`, `action`, `app_context`, ...). Add to that set if you introduce a new string-only arg.
- The API container bakes goals at build time — **rebuild api** after editing prompts or registering a new goal.
- The worker imports `goals/` at startup — **restart worker** after editing prompt_loader.py or any tool code.
- If your goal handles money flows (place_bet, deposit_confirm), put the action in the HIGH-RISK tier in soul.md's risk table — never let it graduate.

## Testing checklist

- [ ] Goal renders without import errors (`uv run python -c "from goals.<id> import ..."`).
- [ ] Starter prompt mentions the right env (build_env, platform, resolution).
- [ ] At least one full happy-path run completes without hitting `login_failed` / `<goal_id>_failed` / `<goal_id>_unverified`.
- [ ] On the second run, native screens are faster (graduated low-risk elements skip verification).
- [ ] `appium_set_value` for any numeric input (OTP, postal code, etc.) succeeds — the int-coercion guard is in place.
- [ ] Failure path tested: deliberately break one selector and confirm the agent recovers via fallback strategies, not by asking the user.

## When to NOT use this skill

- The user wants to fix a bug in an existing goal — just edit the relevant `user.md`. This skill is for *adding* a new capability, not patching one.
- The user wants to change the persona — edit `prompts/persona/soul.md` (one source of truth) instead of touching individual goals.
