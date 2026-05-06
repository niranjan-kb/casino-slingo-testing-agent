from ._deps import get_mcp_manager


async def tap_coordinate(args: dict) -> dict:
    """Tap at specific pixel coordinates using appium_swipe (zero-distance swipe = tap).

    This wraps the appium_swipe workaround so the agent doesn't need to remember the pattern.
    """
    x = int(args.get("x", 0))
    y = int(args.get("y", 0))

    if x <= 0 or y <= 0:
        return {"status": "error", "error": "x and y must be positive integers"}

    manager = get_mcp_manager()
    if not manager or not manager.is_running:
        return {"status": "error", "error": "MCP manager not running. Is appium-mcp started?"}

    result = await manager.call_tool("appium_swipe", {
        "startX": x,
        "startY": y,
        "endX": x,
        "endY": y,
    })

    # Normalize MCP result
    content = str(result.content) if hasattr(result, "content") else str(result)
    return {"status": "success", "tapped": {"x": x, "y": y}, "raw": content}
