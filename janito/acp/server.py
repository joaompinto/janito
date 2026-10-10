"""Newline-delimited JSON-RPC 2.0 server over stdio (ACP stdio transport).

The transport is a pipe: the client (e.g. Zed) spawns ``janito --acp`` and
writes one JSON message per line on stdin while reading responses and
``session/update`` notifications from stdout.  stdout carries *only* ACP
messages; every other log output goes to stderr (handled by the CLI logging
setup).
"""

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from typing import Any

from .agent import JanitoAgent
from .protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    RpcError,
    compact_json,
)

logger = logging.getLogger(__name__)

# Anything printed to stdout by imported libraries would corrupt the ACP
# stream.  The CLI redirects fd 1 to stderr up front (reserve_transport_stdout)
# and saves a duplicate of the original stdout fd here; the writer then wins
# exclusive access to the real pipe.
_transport_fd: int | None = None


def reserve_transport_stdout() -> None:
    """Point fd 1 at stderr for the whole process, keeping the real stdout.

    Called from the CLI entry point before anything can write to stdout (the
    version banner, plugin loading messages, stray prints).  ACP messages are
    written through the saved duplicate of the original fd 1; every other
    output -- including buffered flushes of the old ``sys.stdout`` -- lands on
    stderr.
    """
    global _transport_fd
    _transport_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr


class StdioWriter:
    """Single-line, serialized writer for ACP messages.

    With no ``fd`` (tests) messages go to ``sys.stdout``; the real ACP server
    passes the reserved transport fd so output reaches the client's pipe.
    """

    def __init__(self, fd: int | None = None):
        self._lock = asyncio.Lock()
        self._fd = fd

    async def write(self, payload: dict[str, Any]) -> None:
        data = compact_json(payload) + "\n"
        async with self._lock:
            if self._fd is None:
                sys.stdout.write(data)
                sys.stdout.flush()
            else:
                # Pipes can short-write large payloads; loop until drained.
                remaining = data.encode("utf-8")
                while remaining:
                    written = os.write(self._fd, remaining)
                    remaining = remaining[written:]


async def _iter_stdin_messages() -> AsyncIterator[Any]:
    """Yield decoded JSON messages read line-by-line from stdin."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=64 * 1024 * 1024)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            return
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning("Dropping malformed ACP message: %r", stripped[:200])


class JsonRpcServer:
    """Dispatch JSON-RPC requests / notifications to an ACP agent."""

    def __init__(self, agent: JanitoAgent, writer: StdioWriter | None = None):
        self.agent = agent
        self._writer = writer or StdioWriter()
        self.agent.writer = self._writer
        self._tasks: set[asyncio.Task] = set()

    async def serve_stdio(self) -> None:
        """Run until stdin closes, then cancel in-flight work."""
        try:
            async for message in _iter_stdin_messages():
                await self._on_message(message)
        finally:
            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            # Finish turn cleanup before asyncio.run cancels every remaining
            # task (including shielded worker tasks) and restores the cwd.
            cleanup = asyncio.gather(*tasks, return_exceptions=True)
            while True:
                try:
                    await asyncio.shield(cleanup)
                    break
                except asyncio.CancelledError:
                    continue

    async def _on_message(self, message: Any) -> None:
        if isinstance(message, list):
            for item in message:
                await self._on_message(item)
            return
        if not isinstance(message, dict) or not isinstance(message.get("method"), str):
            if isinstance(message, dict) and "id" in message:
                await self._error_response(message["id"], RpcError(INVALID_REQUEST, "Invalid request"))
            else:
                logger.warning("Ignoring invalid ACP message")
            return

        method = message["method"]
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if "id" in message:
                await self._error_response(message["id"], RpcError(INVALID_PARAMS, "params must be an object"))
            else:
                logger.warning("Dropping ACP notification with non-object params: %s", method)
            return

        if "id" not in message:
            self._spawn(self.agent.handle_notification(method, params), label=f"notification {method}")
            return
        self._spawn(self._dispatch(method, message["id"], params), label=f"request {method}")

    async def _dispatch(self, method: str, request_id: Any, params: dict) -> None:
        try:
            result = await self.agent.handle_request(method, params)
            await self._respond(request_id, result=result)
        except asyncio.CancelledError:
            raise
        except RpcError as error:
            await self._error_response(request_id, error)
        except Exception as error:  # noqa: BLE001 - JSON-RPC boundary
            logger.exception("Internal error handling %s", method)
            await self._error_response(request_id, RpcError(INTERNAL_ERROR, str(error)))

    async def _respond(self, request_id: Any, *, result: Any = None, error: RpcError | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            payload["error"] = {"code": error.code, "message": error.message}
        else:
            payload["result"] = result
        await self._writer.write(payload)

    async def _error_response(self, request_id: Any, error: RpcError) -> None:
        await self._respond(request_id, error=error)

    def _spawn(self, coro, *, label: str) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                logger.error("Unhandled error in %s", label, exc_info=t.exception())

        task.add_done_callback(_done)


def run_acp_agent(args) -> None:
    """Run the ACP stdio agent, blocking for the remainder of the process."""
    from janito.mcp_manager import shutdown_mcp_manager
    from janito.web.backend.config import WebServerConfig

    config = WebServerConfig.from_args(args)
    server = JsonRpcServer(JanitoAgent(config), writer=StdioWriter(fd=_transport_fd))
    try:
        asyncio.run(server.serve_stdio())
    except KeyboardInterrupt:
        pass
    finally:
        if _transport_fd is not None:
            os.close(_transport_fd)
        try:
            shutdown_mcp_manager()
        except Exception:  # noqa: BLE001 - best effort on shutdown
            logger.exception("Failed to shut down MCP servers")
