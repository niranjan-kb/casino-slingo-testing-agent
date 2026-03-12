# Fanatics Casino QA Agent — Contribution Guide

## What This Project Is

An AI QA testing agent for the Fanatics Casino mobile app, built on the [Temporal AI Agent](https://github.com/temporalio/temporal-ai-agent) framework. The agent uses mobile-mcp to interact with an Android device and an LLM to decide what to do based on screenshots.

FBG is a casino operator, not a game studio. We test the app as a platform — game engines are owned by providers. See [constitution](.specify/memory/constitution.md) for the full rationale.

## Repository Layout

### Base framework (unchanged)
- `workflows/` — `AgentGoalWorkflow` (the main agent loop — do not modify for casino-specific logic)
- `activities/` — `ToolActivities` including `mcp_tool_activity` (handles all MCP tool calls)
- `tools/` — Native tool implementations (finance, HR, ecommerce, travel, etc.)
- `models/` — Data types (`AgentGoal`, `MCPServerDefinition`, `ToolDefinition`, etc.)
- `prompts/` — Prompt generators (builds context from goal + tools + history for the LLM)
- `api/` — FastAPI server exposing REST endpoints for the frontend
- `frontend/` — React chat UI at `localhost:5173`
- `shared/mcp_client_manager.py` — Pooled MCP client connections
- `tests/` — Test suite using Temporal's testing framework
- `enterprise/` — .NET worker (not used for casino QA)
- `scripts/` — Utility scripts for running workers and testing tools

### Casino QA additions
- `goals/slingo_qa.py` — Goal definition for Slingo Cash Eruption QA test
- `shared/mcp_config.py` — Updated with `get_mobile_mcp_server_definition()`
- `screen_maps/` — Coordinate knowledge base (JSON, keyed by resolution)
- `the_game.md` — Slingo Cash Eruption game rules, symbols, UI layout
- `rovo-simple-research.md` — FBG internal context from Confluence/Jira
- `.specify/memory/constitution.md` — Architecture decisions and principles
- `example-goal-workflows-activities-signals.md` — Sequence diagram + mobile-mcp tool reference

## Running the Application

### Quick Start with Docker
```bash
# Start all services with development hot-reload
docker compose up -d

# Quick rebuild without infrastructure
docker compose up -d --no-deps --build api worker frontend
```

Default URLs:
- Temporal UI: http://localhost:8080
- API: http://localhost:8000  
- Frontend: http://localhost:5173

### Local Development Setup

1. **Prerequisites:**
   ```bash
   # Install uv and Temporal server (MacOS)
   brew install uv
   brew install temporal

   temporal server start-dev
   ```

2. **Backend (Python):**
   ```bash
   # Quick setup using Makefile
   make setup              # Creates venv and installs dependencies
   make run-worker         # Starts the Temporal worker
   make run-api            # Starts the API server
   
   # Or manually:
   uv sync
   uv run scripts/run_worker.py    # In one terminal
   uv run uvicorn api.main:app --reload   # In another terminal
   ```

3. **Frontend (React):**
   ```bash
   make run-frontend       # Using Makefile
   
   # Or manually:
   cd frontend
   npm install
   npx vite
   ```

4. **Enterprise .NET Worker (optional):**
   ```bash
   make run-enterprise     # Using Makefile
   
   # Or manually:
   cd enterprise
   dotnet build
   dotnet run
   ```

### Environment Configuration
Copy `.env.example` to `.env` and configure:
```bash
# Casino QA mode
AGENT_GOAL=goal_slingo_qa
GOAL_CATEGORIES=casino-qa
SHOW_CONFIRM=True

# LLM Configuration (AWS Bedrock)
LLM_MODEL=bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
AWS_PROFILE=bedrock
AWS_REGION_NAME=us-east-1

# Or use OpenAI/Anthropic directly
# LLM_MODEL=openai/gpt-4o
# LLM_KEY=your-api-key-here

# Other goals (from base framework) still work
# AGENT_GOAL=goal_event_flight_invoice
# GOAL_CATEGORIES=all
```

## Testing

The project includes comprehensive tests using Temporal's testing framework:

```bash
# Install test dependencies
uv sync

# Run all tests
uv run pytest

# Run with time-skipping for faster execution  
uv run pytest --workflow-environment=time-skipping

# Run specific test categories
uv run pytest tests/test_tool_activities.py -v     # Activity tests
uv run pytest tests/test_agent_goal_workflow.py -v # Workflow tests

# Run with coverage
uv run pytest --cov=workflows --cov=activities
```

**Test Coverage:**
- ✅ **Workflow Tests**: AgentGoalWorkflow signals, queries, state management
- ✅ **Activity Tests**: ToolActivities, LLM integration (mocked), environment configuration  
- ✅ **Integration Tests**: End-to-end workflow and activity execution

**Documentation:**
- **Quick Start**: [testing.md](docs/testing.md) - Simple commands to run tests
- **Comprehensive Guide**: [tests/README.md](tests/README.md) - Detailed testing patterns and best practices

## Linting and Code Quality

```bash
# Using poe tasks
uv run poe format    # Format code with black and isort
uv run poe lint      # Check code style and types
uv run poe test      # Run test suite

# Manual commands
uv run black .
uv run isort .
uv run mypy --check-untyped-defs --namespace-packages .
```

## Agent Customization

### Adding New Goals and Tools

#### For Native Tools:
1. Create tool implementation in `tools/` directory
2. Add tool function mapping in `tools/__init__.py`  
3. Register tool definition in `tools/tool_registry.py`
4. Add tool names to static tools list in `workflows/workflow_helpers.py`
5. Create or update goal definition in appropriate file in `goals/` directory

#### For MCP Tools:
1. Configure MCP server definition in `shared/mcp_config.py` (for reusable servers)
2. Create or update goal definition in appropriate file in `goals/` directory with `mcp_server_definition`
3. Set required environment variables (API keys, etc.)

#### For Goals:
1. Create goal file in `goals/` directory (e.g., `goals/my_category.py`)
2. Import and extend the goal list in `goals/__init__.py`

### Configuring Goals
The agent supports multiple goal categories organized in `goals/`:
- **Casino QA**: Mobile game testing via mobile-mcp (`goals/slingo_qa.py`)
- **Financial**: Money transfers, loan applications (`goals/finance.py`)
- **HR**: PTO booking, payroll status (`goals/hr.py`)
- **Travel**: Flight/train booking, event finding (`goals/travel.py`)
- **Ecommerce**: Order tracking, package management (`goals/ecommerce.py`)
- **Food**: Restaurant ordering and cart management (`goals/food.py`)
- **MCP Integrations**: External service integrations like Stripe (`goals/stripe_mcp.py`)

Goals can use:
- **Native Tools**: Custom implementations in `/tools/` directory
- **MCP Tools**: External tools via Model Context Protocol servers (configured in `shared/mcp_config.py`)

See [adding-goals-and-tools.md](docs/adding-goals-and-tools.md) for detailed customization guide.

## Architecture

This system implements agentic AI—autonomous systems that pursue goals through iterative tool use and human feedback—with these key components:
1. **Goals** - High-level objectives accomplished through tool sequences (organized in `/goals/` by category)
2. **Native & MCP Tools** - Custom implementations and external service integrations
3. **Agent Loops** - LLM execution → tool calls → human input → repeat until goal completion
4. **Tool Approval** - Human confirmation for sensitive operations
5. **Conversation Management** - LLM-powered input validation and history summarization
6. **Durability** - Temporal workflows ensure reliable execution across failures

For detailed architecture information, see [architecture.md](docs/architecture.md).

## Commit Messages and Pull Requests
- Use clear commit messages describing the change purpose
- Reference specific files and line numbers when relevant (e.g., `workflows/agent_goal_workflow.py:125`)
- Open PRs describing **what changed** and **why**
- Ensure tests pass before submitting: `uv run pytest --workflow-environment=time-skipping`

## Casino QA-Specific Design Decisions

- **Do not modify `AgentGoalWorkflow`** — all casino-specific logic lives in goal definitions
- **Every device interaction is an MCP tool call** — no raw ADB in workflow code
- **Screen map is domain knowledge in the prompt** — not a separate lookup system
- **Game screens (WebView) are invisible to `list_elements_on_screen`** — use screenshots + LLM vision for in-game interactions, accessibility tree for native app screens only
- **The END GAME button is unreliable** — always use the native header exit button + modal to end rounds

See [constitution](.specify/memory/constitution.md) for the complete set of principles.

## Additional Resources
- **Constitution**: [constitution.md](.specify/memory/constitution.md) - Casino QA architecture decisions and principles
- **Example Flow**: [example-goal-workflows-activities-signals.md](example-goal-workflows-activities-signals.md) - Sequence diagram with mobile-mcp tools
- **Game Rules**: [the_game.md](the_game.md) - Slingo Cash Eruption mechanics and UI reference
- **Setup Guide**: [setup.md](docs/setup.md) - Detailed configuration instructions
- **Architecture Decisions**: [architecture-decisions.md](docs/architecture-decisions.md) - Why Temporal for AI agents