import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

from models.tool_definitions import MCPServerDefinition

# Import MCP client libraries
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None
    sse_client = None

logger = logging.getLogger(__name__)


class MCPClientManager:
    """Persistent MCP connection running in its own asyncio Task.

    appium-mcp ties driver lifecycle to MCP client connection — when the client
    disconnects, all Appium sessions are cleaned up. To keep sessions alive
    across Temporal activity calls (which run in different asyncio Tasks), we
    hold one long-lived SSE connection in a dedicated background task and
    route all tool calls through an asyncio Queue.

    Usage:
        manager = MCPClientManager()
        await manager.start("http://localhost:3100/sse")
        result = await manager.call_tool("appium_screenshot", {})
        await manager.stop()
    """

    def __init__(self):
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        self._sse_url: Optional[str] = None

    async def start(self, sse_url: str) -> None:
        """Start the persistent SSE connection in a background task."""
        if self._task and not self._task.done():
            logger.info("MCPClientManager already running")
            return

        self._sse_url = sse_url
        self._ready.clear()
        self._task = asyncio.create_task(self._run_loop(sse_url))
        await self._ready.wait()
        logger.info(f"MCPClientManager connected to {sse_url}")

    async def _run_loop(self, sse_url: str) -> None:
        """Background task that holds the SSE connection open and processes requests.

        Auto-reconnects on connection loss with exponential backoff.
        Fails any pending futures when the connection drops so callers don't hang.
        """
        backoff = 1  # seconds
        max_backoff = 30

        while True:
            try:
                async with sse_client(sse_url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        logger.info("MCP session initialized in background task")
                        backoff = 1  # reset on successful connection
                        self._ready.set()

                        while True:
                            request = await self._request_queue.get()
                            if request is None:
                                # Shutdown signal
                                logger.info("MCPClientManager shutting down")
                                return  # exit the entire method

                            tool_name, args, future = request
                            try:
                                result = await session.call_tool(
                                    tool_name, arguments=args
                                )
                                if not future.done():
                                    future.set_result(result)
                            except Exception as e:
                                if not future.done():
                                    future.set_exception(e)
            except asyncio.CancelledError:
                logger.info("MCPClientManager task cancelled")
                self._drain_pending_futures("MCPClientManager was cancelled")
                return
            except Exception as e:
                logger.error(f"MCPClientManager connection lost: {e}")
                # Fail any pending futures so callers don't hang forever
                self._drain_pending_futures(f"MCP connection lost: {e}")
                # Signal ready on first connect attempt failure so start() doesn't hang
                if not self._ready.is_set():
                    self._ready.set()
                logger.info(f"Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    def _drain_pending_futures(self, error_msg: str) -> None:
        """Fail all pending futures in the queue so callers don't hang."""
        drained = 0
        while not self._request_queue.empty():
            try:
                item = self._request_queue.get_nowait()
                if item is None:
                    continue
                _, _, future = item
                if not future.done():
                    future.set_exception(ConnectionError(error_msg))
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            logger.warning(f"Drained {drained} pending request(s) after disconnect")

    async def call_tool(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Any:
        """Send a tool call to the persistent MCP session (called from activity tasks)."""
        if not self._task or self._task.done():
            raise RuntimeError(
                "MCPClientManager not running. Call start() first or set APPIUM_MCP_SSE_URL."
            )

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        await self._request_queue.put((tool_name, args, future))
        return await future

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        """Gracefully shut down the background connection."""
        if self._task and not self._task.done():
            await self._request_queue.put(None)
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning("MCPClientManager task cancelled after timeout")
        self._task = None
        logger.info("MCPClientManager stopped")
