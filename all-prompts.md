Here's the complete prompt-layer inventory, organized by where each file plugs into the planner prompt assembly (generate_genai_prompt in prompts/generators.py).

L0 — Persona / Identity (cacheable prefix)
Path	Role
prompts/persona/soul.md	Danny Ocean's identity, values, vibe — the who
prompts/persona/identity.md	Operational identity — what kind of agent (QA, casino, safety rules)
prompts/persona/persona_dials.yaml	Numeric persona knobs (risk tolerance, verbosity, etc.) — read by observers
prompts/persona/init.py	Loader
L1 — Tool definitions (per-call, intent-filtered)
Path	Role
tools/registry/*.yaml (14 files)	Per-tool side-cars — platforms, intents, risk_tier, side_effects. Used by _format_tools for the intent-filter
Tool descriptions baked into tools/tool_registry.py ToolDefinition entries	Human-readable tool args + descriptions shown in the prompt
L2 — Intent declarations
Path	Role
intents/intent_parse_session.md	Compile vague prompt → SessionIntent
intents/intent_authenticate.md	Fanatics ONE 2-step + OTP + home confirm
intents/intent_navigate_to_screen.md	Generic from-any-screen → target signature
intents/intent_navigate_to_game.md	Lobby walk (recents → category → search → scroll)
intents/intent_load_game_context.md	Inject playbook + kind-file as L4
intents/intent_play_game.md	Generic round-loop driver
intents/intent_report.md	Session terminator — emits run report
L3 — Runtime facts (JSON, not markdown)
Path	Role
shared/runtime_facts.py	Dataclasses; serialized as L3 block per turn (~400 tokens). build_env, device, jurisdiction, stop-loss
L4 — Game knowledge (playbook + kind body)
Path	Role
game_kinds/slingo.md	Slingo turn structure, special symbols, joker priority
game_kinds/slots.md	Slot mechanics + provider variants
game_kinds/blackjack.md	RNG blackjack — Fanatics Blackjack, Multi-Hand, Single Hand
game_kinds/roulette.md	RNG roulette — Fanatics Fire Roulette
game_kinds/live_blackjack.md	EVONET live BJ — timed windows, side bets
game_kinds/live_roulette.md	Lightning/Red Door/American live
game_kinds/baccarat.md	Speed Baccarat, Baccarat (EVONET)
game_kinds/live_show.md	Crazy Time, MONOPOLY Deluxe
game_playbook table rows (per-game, auto-populated)	DB; combined with kind body to form L4
L5 — Conversation history (assembled at runtime)
Not a static file — built per turn by _format_history in prompts/generators.py: last-2 verbatim (XML stripped) + older messages summarized to one-line.

Glue / orchestration
Path	Role
prompts/generators.py	The generate_genai_prompt() assembler — combines L0..L5
prompts/init.py	Package init
prompts/README.md	Layer reference doc
goals/casino_session/init.py	Goal config — tool list, MCP server, starter prompt baked into API image at build
goals/casino_session/prompt_loader.py	Loads goal's starter prompt from disk
goals/slingo_qa_android/	Legacy bundled goal — slated for removal once intents fully validated
Reference / inputs (not auto-loaded, used to build prompts above)
Path	Role
fancash_spins.md	Rich knowledge doc about Spin-to-Win feature — input for future app_structure.md
games.md	~100 top games + state availability — input for game_directory seeding decisions
agent-harness.md	Runtime topology — for humans, not prompts
CLAUDE.md	Engineering guide — for AI editors, not prompts
.specify/memory/constitution.md	Architecture rules