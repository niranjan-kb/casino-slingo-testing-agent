# prompts

Everything related to building LLM prompts for the Casino QA agent — both the shared content (persona) and the runtime assembler (generators).

## Layout

```
prompts/
├── persona/          -- shared identity content used by every goal
│   ├── soul.md           -- who Danny Ocean is (values, vibe)
│   ├── identity.md       -- operational identity (QA, casino, safety rules)
│   ├── app_structure.md  -- per-screen mental model of the app, filled
│   │                        iteratively from operator walkthroughs
│   └── persona_dials.yaml-- numeric knobs (risk tolerance, verbosity)
└── generators.py     -- runtime LLM prompt assembler
```

## Two layers, one place

```
goals/<g>/prompts/*.md   -- domain knowledge (tools, user-flow)
prompts/persona/*.md     -- shared identity content
        ↓ (build-time, via goals/<g>/prompt_loader.py)
AgentGoal.description    -- one assembled string baked into the goal
        ↓ (runtime, via prompts.generators)
prompts/generators.py    -- wraps the description in conversation history,
                            tool schemas, decision rules → LLM prompt
        ↓
workflows/agent_goal_workflow.py  -- calls generate_genai_prompt() each turn
```

The two layers don't import each other. The persona is *content*; the generators are *protocol*. They meet in the workflow when the generator receives a fully-assembled goal description.

## Modules

- **`prompts.persona`** — `load`, `render`, `env_context`, `soul_and_identity`. `soul_and_identity()` composes three files into the L0 block: `soul.md` + `identity.md` + `app_structure.md` (cacheable prefix). Consumed by `goals/<g>/prompt_loader.py` at goal build-time.
- **`prompts.generators`** — `generate_genai_prompt()` builds the full system prompt from an `AgentGoal` + conversation history; accepts an optional `game_context={playbook, kind_name}` envelope which becomes the L4 game-knowledge layer (workflow threads it in after `intent_navigate_to_game` completes). Also `generate_tool_completion_prompt()` and `generate_missing_args_prompt()` for mid-conversation tool flow. Consumed by `workflows/`.
