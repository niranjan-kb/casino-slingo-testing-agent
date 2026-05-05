# prompt_engine

Generic LLM prompt assembly layer. Takes an `AgentGoal` (with its domain-specific `.description`) and wraps it in the scaffolding the LLM needs to operate: JSON response format, conversation history, tool schemas, decision logic, and validation.

## How it fits

```
goals/<goal>/prompts/*.md   -- domain knowledge (identity, tools, memory, etc.)
goals/<goal>/prompt_loader  -- assembles markdown into AgentGoal.description
        ↓
prompt_engine/              -- THIS LAYER: generic LLM protocol wrapper
        ↓
workflows/                  -- calls prompt_engine to build the final LLM prompt
```

Goal-specific content lives in `goals/<goal>/prompts/`. This module is goal-agnostic — it doesn't know about Slingo, Appium, or any particular domain.

## Modules

- **agent_prompt_generators.py** — `generate_genai_prompt()` builds the full system prompt from an `AgentGoal` + conversation history. Also provides `generate_tool_completion_prompt()` and `generate_missing_args_prompt()` for mid-conversation tool flow.
