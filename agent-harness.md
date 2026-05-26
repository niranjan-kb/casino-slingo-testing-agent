# Agent Harness — Casino QA Agent

The runtime topology of the casino-slingo-testing-agent after spec 004 (nav-graph + intent layer) ships. Every box is a real process, file, or table you can `grep`, `docker ps`, or `sqlite3` against today.

## 30-second mental model

```
       USER
        │   "play any slingo till you lose $1"
        ▼
   FastAPI ── start_workflow ──▶  TEMPORAL SPINE
                                       │
                                       │  ◀── intent_registry (markdown)
                                       │  ◀── screen_map.db (signatures, transitions, elements)
                                       │
                                       ▼
                             AgentGoalWorkflow loop
                                       │
                       ┌───────────────┼───────────────┐
                       ▼               ▼               ▼
                 plan next        execute tool      observer tick
                  action           (MCP / native)    (side channel)
                       │               │               │
                       ▼               ▼               ▼
                LLM (Bedrock)      Android device    observation_log
                  picks intent +    via appium-mcp     in screen_map.db
                  tool + args
```

The agent is one workflow, walking a graph, picking from a closed set of intents per turn. Every successful step grows the graph.

---

## Full harness (ASCII)

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                  HUMAN LAYER                                  ║
║                                                                               ║
║  React UI (5173) ◀──HTTP──▶  FastAPI (8000) ◀──gRPC──▶  Temporal (7233)        ║
║  /chat /confirm                /start-workflow              ▲                 ║
║  /end-chat                     /send-prompt                 │                 ║
║                                /confirm                     │                 ║
║                                                             │                 ║
╚═════════════════════════════════════════════════════════════│════════════════╝
                                                              │ workflow + activities
╔═════════════════════════════════════════════════════════════│════════════════╗
║                          DURABLE WORKFLOW SPINE              │                 ║
║                                                              ▼                 ║
║   ┌─────────────────────────────────────────────────────────────────────┐    ║
║   │                   AgentGoalWorkflow  (replay-deterministic)         │    ║
║   │                                                                     │    ║
║   │   state:                                                            │    ║
║   │     • conversation_history  • tool_data                             │    ║
║   │     • session_prompt        • active_intent                         │    ║
║   │     • completed_intents     • observation_log                       │    ║
║   │                                                                     │    ║
║   │   queries (read-only):                                              │    ║
║   │     get_session_prompt / get_active_intent / get_completed_intents  │    ║
║   │     get_conversation_history / get_observation_log                  │    ║
║   │                                                                     │    ║
║   │   signals: user_prompt, confirm, end_chat                           │    ║
║   └────────┬──────────────────────┬─────────────────────────┬───────────┘    ║
║            │                      │                         │                ║
║            │ each turn:           │ on confirm:             │ after tool:    ║
║            ▼                      ▼                         ▼                ║
║   ┌──────────────────┐    ┌──────────────────┐    ┌────────────────────┐     ║
║   │ agent_toolPlanner│    │dynamic_tool_activ│    │   run_observers    │     ║
║   │  (LLM activity)  │    │  (MCP + native)  │    │  (side-channel)    │     ║
║   └────────┬─────────┘    └────────┬─────────┘    └─────────┬──────────┘     ║
╚════════════│═══════════════════════│════════════════════════│════════════════╝
             │                       │                        │
             ▼                       ▼                        ▼
   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
   │ LiteLLM ▶ Bedrock│   │ appium-mcp@1.56.3│   │ observers/ registry  │
   │  Sonnet 4.5      │   │ SSE :3100        │   │ (jackpot_icon,       │
   │                  │   │      │           │   │  unknown_screen, …)  │
   │ forced tool-use: │   │      ▼           │   │                      │
   │ plan_next_action │   │ Appium driver    │   │ WRITE-only side      │
   │                  │   │      │           │   │ effect: never halts  │
   │ schema includes: │   │      ▼           │   │ the goal loop.       │
   │  active_intent   │   │ Android emulator │   │                      │
   │  (closed enum)   │   │ (emulator-5554)  │   │                      │
   │  tool (closed)   │   │                  │   │                      │
   │  args, response  │   └────────┬─────────┘   └──────────┬───────────┘
   └────────┬─────────┘            │                        │
            │ active_intent +      │ tap, type, find,       │ observation rows
            │ next + tool          │ swipe, screenshot      │
            │                      │                        │
            ▼                      ▼                        ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │                  SCREEN-MAP DB (data/screen_map.db)                 │
   │                       THE AGENT'S MEMORY                            │
   │                                                                     │
   │   ┌──────────────────┐  ┌────────────────────┐  ┌────────────────┐  │
   │   │ screen_signatures│  │ screen_transitions │  │ screen_elements│  │
   │   │  (where am I?)   │  │  (graph edges)     │  │  (where's X?)  │  │
   │   │                  │  │  from→verb→target  │  │  device, x, y  │  │
   │   │ +build_env       │  │  →to + confidence  │  │  +confidence   │  │
   │   │ +app_package     │  │  +build_env        │  │  +build_env    │  │
   │   └──────────────────┘  └────────────────────┘  └────────────────┘  │
   │                                                                     │
   │   ┌──────────────────┐  ┌────────────────────┐  ┌────────────────┐  │
   │   │   game_catalog   │  │ signature_proposals│  │ observation_log│  │
   │   │  (slug, loop)    │  │  (unknown→named,   │  │  (observer     │  │
   │   │                  │  │   review-gated)    │  │   findings)    │  │
   │   └──────────────────┘  └────────────────────┘  └────────────────┘  │
   │                                                                     │
   │   READ via screen_graph.find_path  (read-time decay: build mismatch │
   │                                     ×0.5, staleness ramp past 30d)  │
   │   WRITE via TapMapped / VerifyTap / FindElement hooks    │
   └─────────────────────────────────────────────────────────────────────┘
                                     ▲
                                     │ hot reads + auto-record
                                     │
   ┌─────────────────────────────────┴──────────────────────────────────┐
   │                      INTENT LAYER (specs/004)                       │
   │                                                                     │
   │   intents/                                                          │
   │   ├── intent_authenticate.md      ◀ ≤600 tok, declarative           │
   │   ├── intent_navigate_to_screen.md  end-state + success_check       │
   │   ├── intent_play_game.md           guardrails, no selectors        │
   │   └── intent_report.md                                              │
   │                                                                     │
   │   Loaded once at worker import → injected per turn into the LLM     │
   │   prompt as the ACTIVE INTENT section + closed-set enum on the      │
   │   plan_next_action schema. Adding a new flow type = a new file.     │
   └─────────────────────────────────────────────────────────────────────┘
```

---

## Per-turn flow (the loop that runs all day)

```
                         ┌──────────────────────────────────┐
                         │   workflow waits on signal/queue │
                         └──────────────────┬───────────────┘
                                            │
            user_prompt OR ###-tagged       │
            re-prompt arrives in queue      │
                                            ▼
            ┌────────────────────────────────────────────────────┐
            │ build context_instructions:                        │
            │   goal + identity + tools + ACTIVE INTENT body +   │
            │   completed_intents + session_prompt + history     │
            └─────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
            ┌────────────────────────────────────────────────────┐
            │ ToolPromptInput {                                  │
            │   prompt, context_instructions,                    │
            │   allowed_tool_names: [...],                       │
            │   allowed_intent_ids: [...]                        │
            │ }                                                  │
            └─────────────────────┬──────────────────────────────┘
                                  │
                                  ▼ activity
            ┌────────────────────────────────────────────────────┐
            │ agent_toolPlanner — LLM with forced tool-use       │
            │   (plan_next_action schema, closed-set enums)      │
            │                                                    │
            │   returns:                                         │
            │     active_intent  (closed-enum)                   │
            │     next ∈ {confirm, question, pick-new-goal,done} │
            │     tool  (closed-enum)                            │
            │     args, response                                 │
            └─────────────────────┬──────────────────────────────┘
                                  │
              ┌───────────────────┼────────────────────┐
              │                   │                    │
              ▼                   ▼                    ▼
        next='confirm'      next='done' &&        next='done' && (no
        run the tool        active_intent         active_intent OR
        via dispatch        != intent_report      intent_report just
              │                   │               completed)
              │                   ▼                    │
              │      append to completed_intents,      │
              │      clear active_intent,              │
              │      ###-prompt: "pick next intent"    │
              │                   │                    │
              │                   ▼                    ▼
              │            (loop continues)       end workflow,
              │                                   return history
              ▼
      ┌──────────────────────────┐
      │ MCP tool? → appium-mcp   │   AUTO-RECORD on every verified tap:
      │ Native?   → tap_mapped /  │   tap_mapped → record_transition_observation
      │            verify_tap /  │   verify_tap → record_transition_observation
      │            find_element/ │   find_element → upsert_element (best-effort)
      │            tap_coord ... │
      └──────────────┬───────────┘
                     │
                     ▼
              tool result
                     │
                     ▼
            ┌────────────────────┐
            │ run_observers tick │ — observers WRITE observations,
            │  (specs/003)       │   never halt the goal loop.
            └────────────────────┘
                     │
                     ▼
              loop back to top
```

---

## Process / port topology

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Mac dev box                                                               │
│                                                                            │
│  Docker compose:                                                           │
│    ├ temporal:7233       (workflow runtime)                                │
│    ├ postgresql           (Temporal backing store)                         │
│    ├ temporal-ui:8080     (live workflow inspector)                        │
│    ├ api:8000             (FastAPI — start/send/confirm/end)               │
│    └ frontend:5173        (React chat UI)                                  │
│                                                                            │
│  Native processes (NOT in Docker — KVM-bound or device-bound):             │
│    ├ npx appium-mcp@1.56.3 --httpStream --port=3100   (PINNED)             │
│    └ uv run scripts/run_worker_android.py                                  │
│         │                                                                  │
│         ├ ToolActivities (LLM via LiteLLM ▶ Bedrock SSO)                   │
│         ├ run_observers, find_games_for_intent, get_play_loop, ...         │
│         ├ AgentGoalWorkflow                                                │
│         └ holds ScreenMapDB connection + MCPClientManager                  │
│                                                                            │
│  ADB-connected device:                                                     │
│    └ emulator-5554        (Pixel 9 Pro, com.betfanatics.casino.test)       │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid version (renders in GitHub / VSCode markdown preview)

```mermaid
flowchart TB
    subgraph Human["Human Layer"]
        UI[React Chat UI :5173]
        API[FastAPI :8000<br/>start-workflow / send-prompt / confirm]
    end

    subgraph Spine["Durable Workflow Spine — Temporal :7233"]
        WF[AgentGoalWorkflow<br/>state: session_prompt, active_intent,<br/>completed_intents, conversation_history]
        Q[get_active_intent<br/>get_completed_intents<br/>get_session_prompt]
        WF -.->|@workflow.query| Q
    end

    subgraph Acts["Activities"]
        Planner[agent_toolPlanner<br/>LLM via LiteLLM]
        Dispatch[dynamic_tool_activity<br/>MCP + native]
        Obs[run_observers<br/>side-channel]
        IntentAct[intent_activity<br/>find_games / get_play_loop]
    end

    subgraph LLM["LLM"]
        Bedrock[Bedrock — Sonnet 4.5<br/>forced tool-use<br/>plan_next_action]
    end

    subgraph Tools["Tool Surface"]
        MCP[appium-mcp :3100<br/>SSE / PINNED 1.56.3]
        Native[tools/slingo_qa/<br/>TapMapped, VerifyTap,<br/>FindElement, TapCoord, ...]
        Device[Android emulator]
    end

    subgraph Memory["Screen-Map DB — data/screen_map.db"]
        Sigs[(screen_signatures<br/>+ build_env / app_package)]
        Trans[(screen_transitions<br/>graph edges + confidence)]
        Elems[(screen_elements<br/>device coords)]
        Cat[(game_catalog<br/>slug, play_loop_json)]
        Props[(signature_proposals<br/>review-gated)]
        ObsLog[(observation_log)]
    end

    subgraph Intents["Intent Registry — intents/"]
        IA[intent_authenticate.md]
        IN[intent_navigate_to_screen.md]
        IP[intent_play_game.md]
        IR[intent_report.md]
    end

    UI --> API
    API -->|start_workflow / signals| WF
    WF --> Planner
    WF --> Dispatch
    WF --> Obs
    WF -.reads.-> Intents
    WF -.reads.-> Cat

    Planner --> Bedrock
    Bedrock -.->|active_intent + next + tool| Planner
    Planner -.->|tool_data| WF

    Dispatch --> MCP
    Dispatch --> Native
    MCP --> Device
    Native --> MCP

    Native -- auto-record --> Trans
    Native -- auto-record --> Elems
    Native -- read-time decay --> Trans
    Obs --> ObsLog
    ObsLog -- scan --> Props

    classDef store fill:#fff8dc,stroke:#aaa
    class Sigs,Trans,Elems,Cat,Props,ObsLog store
```

---

## Where each constitutional rule lives in this picture

| Rule | Lands in |
|---|---|
| **I. Map primary, LLM fallback** | every Native tool reads the map first via `propose_next_step`; LLM only runs when the map can't answer |
| **II. One agent, intents at runtime** | `_INTENT_REGISTRY` + `active_intent` enum on `plan_next_action` |
| **III. Observers never halt** | `_run_observer_tick` is wrapped in try/except in the workflow |
| **IV. Self-healing** | `FindElement` + LLM-fallback path in tools |
| **V. Risk tiers gate confidence** | `screen_map_db.should_verify_tap` |
| **VI. Operational soul in prompts only** | `intents/*.md` ≤600 tokens, no selectors/fallbacks |
| **VII. Human approval at financial boundaries** | `SHOW_CONFIRM` env + workflow `waiting_for_confirm` flag |
| **WF-1** replay determinism | every non-deterministic op (DB, LLM, env) lives in an activity |
| **WF-2** state via queries | the 3 new `@workflow.query` handlers |
| **WF-3** frozen modules | `tool_activities.py` got default-valued additions only — body unchanged |
| **MW-1..4** writeback + decay + proposals | `tools/slingo_qa/*` hooks + `screen_graph._effective_confidence` + `signature_proposals` table |

---

## Reading order if you're new to this codebase

1. `prompts/persona/soul.md` — what the agent *is*
2. `intents/intent_authenticate.md` — what an intent looks like
3. `shared/screen_map_db.py` schema (lines ~670+) — the DB tables
4. `shared/screen_graph.py` `find_path` — how the agent walks the graph
5. `tools/slingo_qa/tap_mapped.py` — the canonical lookup → tap → verify → record loop
6. `workflows/agent_goal_workflow.py` `run()` — the master loop
7. `activities/tool_activities.py` `_build_plan_next_action_tool` — how tool-use forcing works
