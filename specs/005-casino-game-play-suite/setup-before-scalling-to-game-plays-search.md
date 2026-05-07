Session 7fed6987 — what the planner actually sees
Run completed in 23 planner turns / 21 tool dispatches. Total LLM input across the run: ~1.1M chars (~280K tokens). Every turn re-sends the full goal prose + full conversation history.

Evidence — context size growth per turn
Turn	ctx (chars)	prompt (chars)	Notes
1	23,317	436	static prelude only
4	31,406	6,104	tool result (create_session HTML dashboard)
8	38,684	118,254	full XML page-source dump
13	48,943	36,796	another full page-source dump
22	63,766	134,897	another page-source dump
23	65,141	183	39,777 of those chars are "Conversation so far"
The static context_instructions grows 23K → 65K purely because "Conversation so far" pastes every prior tool result verbatim — including page sources >300KB that get truncated to ~134KB each.

1. What should NOT be passed to the planner
Raw appium_get_page_source XML — 134KB per call, 3 calls in this run = ~400KB of input the LLM never reasons over. The page source's only job is to feed FindElementWithFallback; that activity should consume it locally and emit just {found: true, uuid, coords, label} upstream.
Full conversation transcript every turn — 39,777 chars by turn 23. Verbatim tool-result JSON for select_device, create_session, appium_screenshot, etc. is replayed forever.
HTML resource artifacts from appium-mcp (Page Source Inspector, Session Dashboard pages — visible in turn 4 prompt as <!DOCTYPE html>...Monaco...Menlo boilerplate). Pure noise to the LLM.
Tool descriptions for inactive intents — all 21 tools advertised every turn even though intent_authenticate only needs ~8.
All four goal phases (Phase 0/1/2/3) — phases that are already complete remain in the prompt. By turn 22, "Phase 0" is irrelevant context.
Generic "common mistakes" prose — appium_click requires elementUUID not elementId is already enforced by the JSON schema in tool-use forcing. Telling the LLM in prose is belt-and-suspenders that costs tokens.
Claude Code system reminders that leaked through (the <system-reminder>The TodoWrite tool hasn't been used recently...</system-reminder> block ended up inside the workflow prompt at turn 23). That's harness pollution.
2. What should NOT be hardcoded
Currently baked into goals/casino_session/prompts/user.md prose, observable in context_instructions:

Credentials: niranjan.kurambhatti+3@betfanatics.com, Mumbai@2023, OTP 864408 — should come from a RuntimeFacts payload (per workflow start, per build_env).
Build/device facts: test, 1344x2992, com.betfanatics.casino.test — derive from select_device result, don't pre-inject.
The four ### Phase N blocks (~6,400 chars) — these are an executable script in markdown. They duplicate what intents/intent_authenticate.md plus the screen-map graph already encode. Phases should be derived, not authored.
Tool argument shape & "critical names" — already enforced by Anthropic tool_choice schema.
Per-tool 1KB descriptions for select_device (1,017 chars) and create_session (1,233 chars) — these come from appium-mcp's mcp_list_tools. They should be cached and pruned to the active intent.
3. What makes scaling difficult
Linear context growth. Every turn pays for every prior turn. Login is 23 turns. A play-game session with 100 spins becomes >1M tokens of redundant transcript. Sonnet 4.5's 200K window will be exhausted before the agent finishes a real game.
Static tool registry. Adding intent_navigate_to_screen and intent_play_game will push the always-on tool list to ~30. New games add catalog rows but the goal config keeps absorbing prose.
Coupled prose: the goal markdown encodes both identity (SOUL), capabilities (tool docs), runtime config (credentials), and flow control (phases). Each new flow forks the markdown.
Tool result fidelity is uniform. A 300KB page source and a 50-byte WaitSeconds result are stored the same way in conversation history. No tiered retention.
No prompt caching. The first 23KB of every turn (SOUL + tool registry + goal phases) is identical and could be cache_control-pinned in the Anthropic call — saving ~95% of input tokens on turns 2-23.
4. How to improve context per turn
Active-intent gating: load intents/intent_authenticate.md (~600 tokens) only when that intent is active. Drop the other 3.
Active-tools gating: each intent declares allowed_tools in frontmatter — feed only those to tool_choice.
Phase derivation: replace prose phases with current_screen_signature → next_target_signature from shared/screen_graph.py. The goal becomes one line: "reach home_lobby_authenticated from current screen."
Compressed tool history: keep last 1 tool result verbatim, summarize older ones to one structured line: t-3: appium_click(elementUUID=…) → screen=email_entry (verified, conf=0.95).
Never embed page-source XML in the planner prompt. FindElementWithFallback already consumes it locally. The planner only needs the outcome.
Structured runtime facts: pass {email, build_env, resolution, app_pkg, otp} as a JSON block in the schema (or in tool args directly), not in markdown prose.
Strip harness boilerplate before forwarding to the planner — the <system-reminder> blocks and <ide_selection> / <command-name> tags from Claude Code are leaking into workflow prompts.
5. How to make assembly dynamic
The current pipeline (prompts/generators.py) does string concatenation. Replace it with layered, registry-driven assembly:


[L0 persona]              soul.md (cached, never changes per run)
[L1 capabilities]         tool registry filtered by active intent
[L2 intent declaration]   the one active intent file (≤600 tokens)
[L3 runtime facts]        {build_env, resolution, app_pkg, creds_ref} as JSON
[L4 graph state]          {current_signature, target_signature, path_hint}
[L5 working memory]       last-N (default 2) tool results verbatim + 
                          rolling 1-line summary of earlier turns
[L6 latest observation]   what just happened (the prompt)
[L7 instruction]          "decide next via plan_next_action"
Concrete moves to enable this:

Anthropic prompt caching: mark L0+L1 with cache_control: {type: "ephemeral"} — the 24KB static prelude becomes free for turns 2-N within 5 min.
Working-memory compactor: after each tool result, write a 1-line distillation into a WorkingMemory activity-side object. Drop verbatim payloads older than the cutoff. (This is what every long-horizon agent eventually needs — Voyager, MemGPT, etc.)
Goal as state machine: goals/casino_session/__init__.py should expose next_phase(current_state) → phase_descriptor instead of dumping all four phases as markdown.
Intent-conditional tool list: in prompts/generators.py, filter allowed_tool_names by intent.allowed_tools rather than the goal's full tool list.
Ban page-source forwarding: enforce in _normalize_result in activities/tool_activities.py — if tool == appium_get_page_source, return {success, hash, summary: '...XML stored locally, len=N'} instead of the tree.
Split goal markdown: extract ## Test credentials and ## Runtime context out of goals/casino_session/prompts/user.md into a runtime-injected RuntimeFacts object.
Headline numbers
If we apply just three of the above to this exact run:

prompt caching of the 23KB static prelude → ~22 × 23KB ≈ 506KB saved
drop XML page sources from prompts → ~400KB saved
summarize old tool results in conversation history → ~30KB saved
Total: ~940KB / ~235K tokens out of ~280K → >80% reduction with no behavior change.