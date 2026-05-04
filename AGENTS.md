# Agents

This file is the entry point for AI coding assistants reading this repository (Claude Code, Codex, Cursor, etc.).

The full engineering guide — architecture, run commands, design decisions, gotchas, recipe for adding new goals — lives in **[CLAUDE.md](CLAUDE.md)**. We keep one canonical source of truth so the docs don't drift.

The agent's runtime *identity* (who it is, what it cares about, how it thinks) is defined in **[`prompts/persona/soul.md`](prompts/persona/soul.md)**, mirrored from the canonical [SOUL.md](../casino-game-player/SOUL.MD). Read that to understand what the agent is *trying to do*; read CLAUDE.md to understand how the engineering supports it.

## Tl;dr for an AI editor

- This is a **casino game player** built on Temporal for visibility + durability.
- One persona, three to four high-level goals: `goal_login`, `goal_navigate_to_game`, `goal_play_game`, `goal_session_report`.
- Goals are **platform-agnostic capabilities**. Platform/build/resolution differences live in the screen-map DB.
- Output is **structurally enforced** via Anthropic tool-use forcing on a synthetic `plan_next_action` tool — do NOT regress to prompt-prayer JSON.
- **Self-healing is non-negotiable.** Agents never set `next='question'` for routine recovery; alternative selector strategies first.
- Read [CLAUDE.md](CLAUDE.md) before changing any code.
