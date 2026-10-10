"""ACP agent: protocol handlers bridging janito's agentic loop into ACP.

The agent is a plain object answering ACP JSON-RPC methods (``initialize``,
``session/new``, ``session/prompt``) and notifications (``session/cancel``).
Turn execution reuses the web backend's async generator
``janito.web.backend.agent.loop.stream_prompt``; the ``turn_runner`` parameter
allows tests to inject a fake generator.

Concurrency model: one global ``_turn_lock`` serializes every turn and every
``session/new`` system-prompt resolution, and the process cwd is owned by
the lock holder until its tracked sync workers finish.  Sync work (tool
execution, MCP discovery, sync SDK chunk pulls) runs in tracked worker
threads (``janito.web.backend.agent.workers``); cancellation stops the async
turn promptly but drains the workers -- shielded from repeated cancels --
before restoring cwd, releasing the lock, and rolling the history back.
"""

import asyncio
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from janito.conversation_utils import rollback_to_last_turn
from janito.web.backend.agent.loop import stream_prompt
from janito.web.backend.agent.workers import WorkerTracker, drain_shielded, reset_tracker, set_tracker
from janito.web.backend.config import WebServerConfig
from janito.web.backend.events import ErrorEvent

from .events import map_event, text_block
from .protocol import INTERNAL_ERROR, INVALID_PARAMS, METHOD_NOT_FOUND, RpcError

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1

TurnRunner = Callable[..., AsyncGenerator]


@dataclass
class AcpSession:
    """The per-client-session conversation state."""

    session_id: str
    cwd: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    # Turn-start markers (history length before each turn); a cancelled /
    # failed turn rolls back to the most recent one (mirrors the web
    # backend's ``history_turns``).
    history_turns: list[int] = field(default_factory=list)


def blocks_to_text(blocks) -> str:
    """Convert ACP prompt content blocks into a plain-text user message."""
    parts = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "resource":
            resource = block.get("resource") or {}
            text = resource.get("text")
            uri = resource.get("uri", "")
            if text:
                parts.append(f"{text}\n[source: {uri}]" if uri else text)
            elif uri:
                parts.append(f"[source: {uri}]")
        elif block_type == "resource_link":
            parts.append(f"[Referenced file: {block.get('uri', '')}]")
        elif block_type in ("image", "audio"):
            parts.append(f"[{block_type} content ignored: janito has no {block_type} input capability]")
        else:
            continue
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


class JanitoAgent:
    """ACP agent backed by janito's web-loop turn runner."""

    def __init__(
        self,
        config: WebServerConfig,
        *,
        turn_runner: TurnRunner | None = None,
        writer=None,
    ):
        self.config = config
        self._turn_runner = turn_runner or stream_prompt
        self.writer = writer  # a StdioWriter, wired up by JsonRpcServer
        self._sessions: dict[str, AcpSession] = {}
        self._running: dict[str, asyncio.Task] = {}
        # Serializes turns and session/new prompt resolution, and scopes
        # chdir ownership (see _run_turn / _new_session).
        self._turn_lock = asyncio.Lock()

    def _agent_info(self) -> dict[str, Any]:
        from janito._version import __version__

        return {"name": "janito", "title": "Janito", "version": __version__}

    async def handle_request(self, method: str, params: dict) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "session/new":
            return await self._new_session(params)
        if method == "session/prompt":
            return await self._prompt(params)
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    async def handle_notification(self, method: str, params: dict) -> None:
        if method == "session/cancel":
            self._cancel(params)
            return
        logger.debug("Ignoring unknown ACP notification: %s", method)

    def _initialize(self, params: dict) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": True,
                },
                "mcpCapabilities": {"http": False, "sse": False},
            },
            "agentInfo": self._agent_info(),
            "authMethods": [],
        }

    async def _new_session(self, params: dict) -> dict[str, Any]:
        cwd = params.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            raise RpcError(INVALID_PARAMS, "cwd is required and must be an absolute path")
        if not os.path.isabs(cwd):
            raise RpcError(INVALID_PARAMS, f"cwd must be an absolute path, got: {cwd!r}")

        mcp_servers = params.get("mcpServers") or []
        if mcp_servers:
            logger.warning(
                "session/new provided %d MCP server(s); janito uses its own configured "
                "MCP services and ignores the provided ones",
                len(mcp_servers),
            )

        # Resolve the project prompt under the same turn lock and the
        # requested cwd: waits for any active turn (no cwd race), and the
        # cwd AGENTS.md / config start is read from the session's project,
        # not the server's launch directory.
        async with self._turn_lock:
            previous_cwd = os.getcwd()
            need_chdir = os.path.abspath(previous_cwd) != os.path.abspath(cwd)
            if need_chdir:
                try:
                    os.chdir(cwd)
                except OSError as exc:
                    raise RpcError(INVALID_PARAMS, f"cwd is not accessible: {cwd!r} ({exc})") from exc
            try:
                system_prompt = self.config.get_effective_system_prompt()
            finally:
                if need_chdir:
                    os.chdir(previous_cwd)

        session = AcpSession(session_id=uuid.uuid4().hex, cwd=cwd)
        if system_prompt and not self.config.no_system_prompt:
            session.messages.append({"role": "system", "content": system_prompt})
        self._sessions[session.session_id] = session
        return {"sessionId": session.session_id}

    async def _prompt(self, params: dict) -> dict[str, Any]:
        session = self._require_session(params)
        prompt_blocks = params.get("prompt")
        if not isinstance(prompt_blocks, list):
            raise RpcError(INVALID_PARAMS, "prompt must be an array of content blocks")
        text = blocks_to_text(prompt_blocks)
        if not text:
            raise RpcError(INVALID_PARAMS, "prompt contains no supported content")

        task = asyncio.current_task()
        if task is None:
            raise RpcError(INTERNAL_ERROR, "session/prompt must run inside a task")
        # Atomic same-session registration: no await between check and set,
        # so overlapping prompts on one session are rejected instead of
        # overwriting each other's cancel registration.
        if session.session_id in self._running:
            raise RpcError(INVALID_PARAMS, f"prompt already running for session: {session.session_id!r}")
        self._running[session.session_id] = task
        # Record the turn start before the turn mutates history; a
        # cancelled / failed turn rolls back to it.
        session.history_turns.append(len(session.messages))
        try:
            saw_error = await self._run_turn(session, text)
        except asyncio.CancelledError:
            logger.info("Prompt for session %s cancelled", session.session_id)
            rollback_to_last_turn(session.messages, session.history_turns)
            return {"stopReason": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - boundary: report, then end turn
            logger.exception("Prompt for session %s failed", session.session_id)
            rollback_to_last_turn(session.messages, session.history_turns)
            await self._notify(
                session.session_id,
                {"sessionUpdate": "agent_message_chunk", "content": text_block(f"Agent error: {exc}")},
            )
        else:
            if saw_error:
                rollback_to_last_turn(session.messages, session.history_turns)
        finally:
            # Release the session only after cancellation cleanup finishes.
            if self._running.get(session.session_id) is task:
                self._running.pop(session.session_id, None)
        return {"stopReason": "end_turn"}

    def _require_session(self, params: dict) -> AcpSession:
        session_id = params.get("sessionId")
        session = self._sessions.get(session_id)
        if session is None:
            raise RpcError(INVALID_PARAMS, f"Unknown session: {session_id!r}")
        return session

    def _cancel(self, params: dict) -> None:
        session_id = params.get("sessionId")
        task = self._running.get(session_id)
        if task is not None:
            logger.info("Cancelling running prompt for session %s", session_id)
            task.cancel()

    async def _run_turn(self, session: AcpSession, text: str) -> bool:
        """Run one turn with the session's cwd applied, restoring on exit.

        Returns ``True`` when the turn streamed an :class:`ErrorEvent`
        (the caller rolls the history back).  The cwd is owned until every
        tracked sync worker finishes: cancellation stops the async turn
        promptly, then the workers are drained -- shielded from repeated
        cancels -- before cwd restore / lock release.
        """
        async with self._turn_lock:
            previous_cwd = os.getcwd()
            need_chdir = os.path.abspath(previous_cwd) != os.path.abspath(session.cwd)
            if need_chdir:
                os.chdir(session.cwd)
            tracker = WorkerTracker()
            token = set_tracker(tracker)
            saw_error = False
            was_cancelled = False
            try:
                try:
                    saw_error = await self._stream_turn(session, text)
                except asyncio.CancelledError:
                    was_cancelled = True
            finally:
                # Drain sync workers before restoring cwd / releasing the
                # lock; repeated cancels must not interrupt cleanup.
                was_cancelled |= await drain_shielded(tracker)
                # Reset the context var and restore cwd even if draining
                # saw (and swallowed) repeated cancels.
                reset_tracker(token)
                if need_chdir:
                    os.chdir(previous_cwd)
            if was_cancelled:
                raise asyncio.CancelledError
            return saw_error

    async def _stream_turn(self, session: AcpSession, text: str) -> bool:
        """Stream one turn's events; return True when an ErrorEvent fired."""
        message_id = uuid.uuid4().hex[:16]
        saw_error = False
        async for event in self._turn_runner(text, session.messages, self.config):
            if isinstance(event, ErrorEvent):
                saw_error = True
            update = map_event(event, message_id=message_id, cwd=session.cwd)
            if update:
                await self._notify(session.session_id, update)
        return saw_error

    async def _notify(self, session_id: str, update: dict[str, Any]) -> None:
        if self.writer is None:
            return
        await self.writer.write(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": session_id, "update": update},
            }
        )
