import asyncio
import concurrent.futures
import logging
import os

from dotenv import load_dotenv

# Load env first, then derive queue/goal before importing shared.config
load_dotenv(override=True)

_platform = os.getenv("PLATFORM", "android").lower()
os.environ.setdefault("TEMPORAL_TASK_QUEUE", f"casino-qa-{_platform}")
os.environ.setdefault("AGENT_GOAL", f"goal_slingo_qa_{_platform}")

print(f"Platform: {_platform}")
print(f"Task queue: {os.environ['TEMPORAL_TASK_QUEUE']}")
print(f"Agent goal: {os.environ['AGENT_GOAL']}")

# Imports after env setup so shared.config reads the correct TEMPORAL_TASK_QUEUE
from temporalio.worker import Worker  # noqa: E402

from activities.intent_activity import (  # noqa: E402
    find_games_for_intent,
    get_play_loop,
    is_intent_reachable,
    list_intent_registry_summary,
    load_runtime_facts_activity,
    record_intent_transition,
    set_plan_graph,
    set_screen_db as set_intent_screen_db,
)
from activities.observer_activity import (  # noqa: E402
    run_observers,
    set_persona as set_observer_persona,
    set_screen_db as set_observer_screen_db,
)
from activities.tool_activities import (  # noqa: E402
    ToolActivities,
    dynamic_tool_activity,
    mcp_list_tools,
    set_persistent_mcp_manager,
)
from observers.persona import load_persona_dials  # noqa: E402
from shared.config import TEMPORAL_TASK_QUEUE, get_temporal_client  # noqa: E402
from shared.mcp_client_manager import MCPClientManager  # noqa: E402
from shared.screen_map_db import ScreenMapDB  # noqa: E402
from tools.casino_qa._deps import set_mcp_manager, set_screen_db  # noqa: E402
from workflows.agent_goal_workflow import AgentGoalWorkflow  # noqa: E402


async def main():
    llm_model = os.environ.get("LLM_MODEL", "openai/gpt-4o")
    print(f"Worker will use LLM model: {llm_model}")

    # Resolve ANDROID_SERIAL from running adb devices (last-used, else first).
    # Skip if the user pinned one explicitly via env.
    if not os.getenv("ANDROID_SERIAL"):
        from shared.device_picker import list_online_devices, pick_android_device

        online = list_online_devices()
        chosen = pick_android_device()
        if chosen:
            os.environ["ANDROID_SERIAL"] = chosen
            others = [s for s in online if s != chosen]
            extra = f" (also online: {', '.join(others)})" if others else ""
            print(f"Android device: {chosen}{extra}")
        else:
            print("WARNING: no online adb devices found — falling back to default 'emulator-5554'")
    else:
        print(f"Android device: {os.environ['ANDROID_SERIAL']} (from env)")

    # Initialize screen map DB (self-improving coordinate storage)
    screen_db = ScreenMapDB()
    stats = screen_db.get_stats()
    print(f"Screen map DB: {screen_db.db_path} ({stats})")

    # Rebuild the goal with DB-powered coordinates
    from goals.slingo_qa_android import build_goal  # noqa: E402
    db_goal = build_goal(screen_db)
    # Patch into the global goal list so the workflow picks it up
    from goals import goal_list  # noqa: E402
    for i, g in enumerate(goal_list):
        if g.id == "goal_slingo_qa_android":
            goal_list[i] = db_goal
            print(f"Replaced goal with DB-powered version ({len(db_goal.description)} chars)")
            break

    mcp_client_manager = MCPClientManager()

    # Start persistent SSE connection if configured
    sse_url = os.getenv("APPIUM_MCP_SSE_URL")
    if sse_url:
        print(f"Starting persistent MCP connection to {sse_url}")
        try:
            await mcp_client_manager.start(sse_url)
            set_persistent_mcp_manager(mcp_client_manager)
            print(f"Persistent MCP connection established to {sse_url}")
        except Exception as e:
            print(f"WARNING: Failed to start persistent MCP connection: {e}")
            print("Falling back to ephemeral connections (sessions won't persist)")

    # Inject shared resources into Slingo QA tools
    set_screen_db(screen_db)
    set_mcp_manager(mcp_client_manager)
    print("Slingo QA tools: ScreenMapDB and MCPClientManager injected")

    # Observer framework wiring (specs/003-observer-framework). Loads persona
    # dials once per worker start and injects them + the screen_db into the
    # run_observers activity's module-level state.
    persona_dials = load_persona_dials()
    set_observer_screen_db(screen_db)
    set_observer_persona(persona_dials.view())
    print(
        f"Observer framework: persona curiosity={persona_dials.curiosity}, "
        f"jackpot_optin={persona_dials.jackpot_optin}, "
        f"max_loss=${persona_dials.max_session_loss_usd}"
    )

    # Intent layer wiring (specs/004-nav-graph-intents). The registry is loaded
    # at workflow-module import time (replay-safe pattern); intent_activity
    # provides DB-backed helpers (catalog lookup, play_loop fetch).
    set_intent_screen_db(screen_db)
    from intents import load_registry  # noqa: E402
    intent_count = len(load_registry())
    print(f"Intent layer: {intent_count} intents in registry")

    # Spec 005 (T016 / T031): plan-graph guard wiring. The activity reads its
    # graph via a module-level singleton set at worker startup (replay-safe —
    # same file on disk yields the same dict every restart). Workflows decide
    # whether to consult the guard based on their own `plan_graph` state, so
    # registering the graph here is harmless for goals that don't use it.
    try:
        import yaml  # noqa: E402

        graphs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "graphs")
        plan_graph_loaded = None
        # Convention: the casino-session goal loads graphs/casino_session.yaml.
        # Other goals can wire their own with one row in this dict.
        plan_graph_path = os.path.join(graphs_dir, "casino_session.yaml")
        if os.path.isfile(plan_graph_path):
            with open(plan_graph_path) as f:
                plan_graph_loaded = yaml.safe_load(f)
        if plan_graph_loaded:
            set_plan_graph(plan_graph_loaded)
            print(f"Plan graph: {len(plan_graph_loaded.get('nodes', {}))} nodes loaded")
        else:
            print("Plan graph: none (legacy goal mode)")
    except Exception as exc:
        # Failing to load the plan graph must NOT block worker startup —
        # the workflow guard falls open per Constitution III.
        print(f"Plan graph load skipped: {exc}")

    client = await get_temporal_client()
    activities = ToolActivities(mcp_client_manager)

    print("Android worker ready to process tasks!")
    logging.basicConfig(level=logging.INFO)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as activity_executor:
            worker = Worker(
                client,
                task_queue=TEMPORAL_TASK_QUEUE,
                workflows=[AgentGoalWorkflow],
                activities=[
                    activities.agent_validatePrompt,
                    activities.agent_toolPlanner,
                    activities.get_wf_env_vars,
                    activities.mcp_tool_activity,
                    dynamic_tool_activity,
                    mcp_list_tools,
                    run_observers,
                    find_games_for_intent,
                    get_play_loop,
                    list_intent_registry_summary,
                    # Spec 005 (T016, T031, T013-thread): plan-graph guard,
                    # RuntimeFacts envelope, intent transition log.
                    is_intent_reachable,
                    load_runtime_facts_activity,
                    record_intent_transition,
                ],
                activity_executor=activity_executor,
            )
            print(f"Starting worker, connecting to task queue: {TEMPORAL_TASK_QUEUE}")
            await worker.run()
    finally:
        screen_db.close()
        await mcp_client_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
