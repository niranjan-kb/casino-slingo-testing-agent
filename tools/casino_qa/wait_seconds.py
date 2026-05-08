import asyncio


async def wait_seconds(args: dict) -> dict:
    """Pause execution for a specified number of seconds."""
    seconds = float(args.get("seconds", 2))
    seconds = min(seconds, 30)  # cap at 30s to prevent abuse
    await asyncio.sleep(seconds)
    return {"status": "success", "waited": seconds}
