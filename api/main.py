import asyncio
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from temporalio.api.enums.v1 import WorkflowExecutionStatus
from temporalio.client import Client
from temporalio.exceptions import TemporalError

from goals import goal_list
from models.data_types import AgentGoalWorkflowParams, CombinedInput
from shared.config import TEMPORAL_TASK_QUEUE, get_temporal_client
from workflows.agent_goal_workflow import AgentGoalWorkflow

app = FastAPI()
temporal_client: Optional[Client] = None

# Load environment variables
load_dotenv()


def get_initial_agent_goal():
    """Get the agent goal from environment variables."""
    env_goal = os.getenv(
        "AGENT_GOAL", "goal_event_flight_invoice"
    )  # if no goal is set in the env file, default to single agent mode
    for listed_goal in goal_list:
        if listed_goal.id == env_goal:
            return listed_goal


@app.on_event("startup")
async def startup_event():
    global temporal_client
    temporal_client = await get_temporal_client()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SCREENSHOTS_DIR = os.path.join(os.getcwd(), "screenshots")
SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg"}


@app.get("/")
def root():
    return {"message": "Temporal AI Agent!"}


@app.get("/screenshots")
def list_screenshots(limit: int = 50):
    """List captured screenshots, newest first."""
    if not os.path.isdir(SCREENSHOTS_DIR):
        return {"screenshots": []}

    entries = []
    for name in os.listdir(SCREENSHOTS_DIR):
        ext = os.path.splitext(name)[1].lower()
        if ext not in SCREENSHOT_EXTS:
            continue
        path = os.path.join(SCREENSHOTS_DIR, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        entries.append({
            "filename": name,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        })

    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return {"screenshots": entries[:limit]}


@app.get("/screenshots/{filename}")
def get_screenshot(filename: str):
    """Serve a screenshot file by name."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SCREENSHOT_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    path = os.path.join(SCREENSHOTS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type)


@app.get("/tool-data")
async def get_tool_data():
    """Calls the workflow's 'get_tool_data' query."""
    try:
        # Get workflow handle
        handle = temporal_client.get_workflow_handle("agent-workflow")

        # Check if the workflow is completed
        workflow_status = await handle.describe()
        if workflow_status.status == 2:
            # Workflow is completed; return an empty response
            return {}

        # Query the workflow
        tool_data = await handle.query("get_latest_tool_data")
        return tool_data
    except TemporalError as e:
        # Workflow not found; return an empty response
        print(e)
        return {}


@app.get("/get-conversation-history")
async def get_conversation_history():
    """Calls the workflow's 'get_conversation_history' query."""
    try:
        handle = temporal_client.get_workflow_handle("agent-workflow")

        failed_states = [
            WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TERMINATED,
            WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CANCELED,
            WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_FAILED,
        ]

        description = await handle.describe()
        if description.status in failed_states:
            print("Workflow is in a failed state. Returning empty history.")
            return []

        # Set a timeout for the query
        try:
            conversation_history = await asyncio.wait_for(
                handle.query("get_conversation_history"),
                timeout=5,  # Timeout after 5 seconds
            )
            return conversation_history
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=404,
                detail="Temporal query timed out (worker may be unavailable).",
            )

    except TemporalError as e:
        error_message = str(e)
        print(f"Temporal error: {error_message}")

        # If worker is down or no poller is available, return a 404
        if "no poller seen for task queue recently" in error_message:
            raise HTTPException(
                status_code=404, detail="Workflow worker unavailable or not found."
            )

        if "workflow not found" in error_message:
            await start_workflow()
            return []
        else:
            # For other Temporal errors, return a 500
            raise HTTPException(
                status_code=500, detail="Internal server error while querying workflow."
            )


@app.get("/agent-goal")
async def get_agent_goal():
    """Calls the workflow's 'get_agent_goal' query."""
    try:
        # Get workflow handle
        handle = temporal_client.get_workflow_handle("agent-workflow")

        # Check if the workflow is completed
        workflow_status = await handle.describe()
        if workflow_status.status == 2:
            # Workflow is completed; return an empty response
            return {}

        # Query the workflow
        agent_goal = await handle.query("get_agent_goal")
        return agent_goal
    except TemporalError as e:
        # Workflow not found; return an empty response
        print(e)
        return {}


@app.post("/send-prompt")
async def send_prompt(prompt: str):
    # Create combined input with goal from environment
    combined_input = CombinedInput(
        tool_params=AgentGoalWorkflowParams(None, None),
        agent_goal=get_initial_agent_goal(),
        # change to get from workflow query
    )

    workflow_id = "agent-workflow"

    # Start (or signal) the workflow
    await temporal_client.start_workflow(
        AgentGoalWorkflow.run,
        combined_input,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
        start_signal="user_prompt",
        start_signal_args=[prompt],
    )

    return {"message": f"Prompt '{prompt}' sent to workflow {workflow_id}."}


@app.post("/confirm")
async def send_confirm():
    """Sends a 'confirm' signal to the workflow."""
    workflow_id = "agent-workflow"
    handle = temporal_client.get_workflow_handle(workflow_id)
    await handle.signal("confirm")
    return {"message": "Confirm signal sent."}


@app.post("/end-chat")
async def end_chat():
    """Sends a 'end_chat' signal to the workflow."""
    workflow_id = "agent-workflow"

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal("end_chat")
        return {"message": "End chat signal sent."}
    except TemporalError as e:
        print(e)
        # Workflow not found; return an empty response
        return {}


@app.post("/start-workflow")
async def start_workflow():
    initial_agent_goal = get_initial_agent_goal()

    # Create combined input
    combined_input = CombinedInput(
        tool_params=AgentGoalWorkflowParams(None, None),
        agent_goal=initial_agent_goal,
    )

    workflow_id = "agent-workflow"

    # Terminate any existing workflow so we get a clean conversation history
    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status == WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING:
            await handle.terminate(reason="Restarting with fresh workflow")
            # Brief pause to let Temporal process the termination
            await asyncio.sleep(0.5)
    except Exception:
        pass  # No existing workflow, that's fine

    # Start a fresh workflow with the starter prompt from the goal
    await temporal_client.start_workflow(
        AgentGoalWorkflow.run,
        combined_input,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
        start_signal="user_prompt",
        start_signal_args=["### " + initial_agent_goal.starter_prompt],
    )

    return {
        "message": f"Workflow started with goal's starter prompt: {initial_agent_goal.starter_prompt}."
    }
