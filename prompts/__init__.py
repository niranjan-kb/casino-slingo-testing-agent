"""Prompt construction for the Casino QA agent.

Two layers live here:

- ``prompts.persona`` — shared identity content (soul.md, identity.md, dials).
  Consumed at goal build-time by ``goals/<g>/prompt_loader.py``.
- ``prompts.generators`` — runtime LLM prompt assembler. Consumed per-turn by
  ``workflows/`` to wrap an ``AgentGoal.description`` in conversation history,
  tool schemas, and decision rules.

The two layers do not import each other; they meet in the workflow when the
generator receives a fully-assembled goal description.
"""
