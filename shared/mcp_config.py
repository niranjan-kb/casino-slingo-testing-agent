import os

from models.tool_definitions import MCPServerDefinition


def get_mobile_mcp_server_definition(
    included_tools: list[str],
) -> MCPServerDefinition:
    """
    Returns a mobile-mcp server definition for Android/iOS device interaction.

    Args:
        included_tools: List of tool names to include from the mobile-mcp server

    Returns:
        MCPServerDefinition configured for mobile-mcp
    """
    return MCPServerDefinition(
        name="mobile-mcp",
        command="npx",
        args=["-y", "@anthropic/mobile-mcp@latest"],
        env=None,
        included_tools=included_tools,
    )


def get_appium_mcp_server_definition(
    platform: str,
    included_tools: list[str],
) -> MCPServerDefinition:
    """
    Returns an appium-mcp server definition for Android or iOS device interaction.

    Args:
        platform: "android" or "ios"
        included_tools: List of tool names to include from the appium-mcp server

    Returns:
        MCPServerDefinition configured for appium-mcp
    """
    # Use SSE transport (persistent server) if APPIUM_MCP_SSE_URL is set,
    # otherwise fall back to stdio (new process per call — no session persistence).
    sse_url = os.getenv("APPIUM_MCP_SSE_URL")  # e.g. "http://localhost:3100/sse"

    return MCPServerDefinition(
        name="appium-mcp",
        command="npx",
        args=["-y", "appium-mcp"],
        env=None,  # inherit full parent environment (PATH, ANDROID_HOME, etc.)
        connection_type="sse" if sse_url else "stdio",
        sse_url=sse_url,
        included_tools=included_tools,
    )


def get_playwright_mcp_server_definition(
    included_tools: list[str],
) -> MCPServerDefinition:
    """
    Returns a @playwright/mcp server definition for browser-based web testing.

    Args:
        included_tools: List of tool names to include from the playwright-mcp server

    Returns:
        MCPServerDefinition configured for @playwright/mcp
    """
    return MCPServerDefinition(
        name="playwright-mcp",
        command="npx",
        args=["-y", "@playwright/mcp@latest"],
        env={
            "BROWSERSTACK_PLAYWRIGHT_URL": os.getenv("BROWSERSTACK_PLAYWRIGHT_URL", ""),
        },
        included_tools=included_tools,
    )


def get_stripe_mcp_server_definition(included_tools: list[str]) -> MCPServerDefinition:
    """
    Returns a Stripe MCP server definition with customizable included tools.

    Args:
        included_tools: List of tool names to include from the Stripe MCP server

    Returns:
        MCPServerDefinition configured for Stripe
    """
    return MCPServerDefinition(
        name="stripe-mcp",
        command="npx",
        args=[
            "-y",
            "@stripe/mcp",
            "--tools=all",
            f"--api-key={os.getenv('STRIPE_API_KEY')}",
        ],
        env=None,
        included_tools=included_tools,
    )
