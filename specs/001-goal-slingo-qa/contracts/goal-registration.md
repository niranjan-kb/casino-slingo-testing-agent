# Contract: Goal Registration

**Type**: Internal module interface
**Producer**: `goals/slingo_qa.py`
**Consumer**: `goals/__init__.py`

## Contract

The `goals/slingo_qa.py` module MUST export a list named `slingo_qa_goals` of type `List[AgentGoal]`.

```python
# goals/slingo_qa.py exports:
slingo_qa_goals: List[AgentGoal] = [goal_slingo_qa]
```

`goals/__init__.py` imports and extends `goal_list`:

```python
from goals.slingo_qa import slingo_qa_goals
goal_list.extend(slingo_qa_goals)
```

## Constraints

- The `id` field (`"goal_slingo_qa"`) must be unique across all goals in `goal_list`
- The `category_tag` field (`"casino-qa"`) must be included in `GOAL_CATEGORIES` env var for the goal to appear
- The `mcp_server_definition` must use `get_mobile_mcp_server_definition()` from `shared/mcp_config.py`
