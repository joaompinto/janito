"""Chat endpoints: session CRUD + WebSocket streaming.

The WebSocket handler is intentionally a thin dispatcher: connection setup,
greeting, and the per-turn cancel/rollback machinery live in small helpers
so the main loop reads top to bottom.
"""

import copy
import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from janito.config_loaders import load_model_from_config
from janito.providers.registry import get_provider

from ..agent.loop import stream_prompt
from ..events import PromptStartedEvent, event_to_dict
from ..prompts import PromptRegistry
from ..session import ConversationSession, SessionManager
from .chat_helpers import _read_client_message, _run_prompt_turn, _send_session_greeting

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


def _get_config(request: Request):
    return request.app.state.config


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


@router.post("/sessions")
async def create_session(request: Request):
    """Create a new conversation session."""
    sessions = _get_sessions(request)
    session = sessions.create()
    return session.to_summary()


@router.get("/sessions")
async def list_sessions(request: Request):
    """List active sessions."""
    sessions = _get_sessions(request)
    return {"sessions": [s.to_summary() for s in sessions.list_sessions()]}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """Get a session's full history."""
    sessions = _get_sessions(request)
    session = sessions.get(session_id)
    if not session:
        return JSONResponse({"detail": "Session not found"}, status_code=404)
    return session.to_dict()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a session."""
    sessions = _get_sessions(request)
    ok = sessions.delete(session_id)
    if not ok:
        return JSONResponse({"detail": "Session not found"}, status_code=404)
    return {"deleted": session_id}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, request: Request):
    """Rename a session."""
    sessions = _get_sessions(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    title = body.get("title", "")
    if sessions.set_title(session_id, title):
        return {"session_id": session_id, "title": title}
    return JSONResponse({"detail": "Session not found"}, status_code=404)


# ---------------------------------------------------------------------------
# WebSocket streaming
# ---------------------------------------------------------------------------


async def _accept_session(websocket: WebSocket, session_id: str) -> ConversationSession | None:
    """Accept the socket and resolve its session, or close with an error."""
    logger.warning("[ws] handshake received session=%s client=%s", session_id, websocket.client)
    await websocket.accept()
    logger.warning("[ws] accepted session=%s", session_id)

    sessions: SessionManager = websocket.app.state.sessions
    session = sessions.get(session_id)
    if not session:
        logger.warning(
            "[ws] session NOT FOUND: %s (known=%s)",
            session_id,
            [s.session_id for s in sessions.list_sessions()],
        )
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return None
    return session


async def _handle_restart(
    session: ConversationSession,
    sessions: SessionManager,
    session_id: str,
    websocket: WebSocket,
) -> None:
    """Restart the session (clear history) and confirm to the client."""
    session.restart()
    sessions.persist(session)  # mirror the cleared history to disk
    await websocket.send_json({"type": "restarted"})


def _maybe_auto_title(
    sessions: SessionManager,
    session_id: str,
    session: ConversationSession,
    content: str,
) -> None:
    """Auto-title the session from the first user prompt."""
    if session.title == "New conversation":
        sessions.set_title(session_id, content[:60])


async def _process_prompt(
    session: ConversationSession,
    websocket: WebSocket,
    config,
    content: str,
    pending_prompts: list[str],
    sessions: SessionManager,
    prompt_registry: PromptRegistry | None = None,
) -> None:
    """Process one user prompt, draining any prompts queued meanwhile.

    Prompts that arrive while a turn is running are queued by
    ``_await_cancel`` (instead of being silently discarded) and are
    processed once the current turn finishes, so a submission is never
    lost mid-stream.
    """
    # Sending a prompt is activity: keep the session fresh for TTL reaping
    # (get() touches on lookup, but a long-lived tab reuses the same
    # session object, so without this an actively-used session could look
    # idle and be evicted mid-conversation).
    session.touch()
    # Pin provider/model before the first user message. Use a shallow config
    # copy so concurrent conversations cannot overwrite the global web config.
    if session.provider is None:
        session.provider = config.effective_provider
        session.model = config.model or load_model_from_config(session.provider)
        if not session.model:
            found = get_provider(session.provider)
            session.model = found.default_model() if found is not None else None
        sessions.persist(session)
    turn_config = copy.copy(config)
    turn_config.session_provider = session.provider
    turn_config.provider = session.provider
    turn_config.model = session.model

    _maybe_auto_title(sessions, session.session_id, session, content)
    steering_prompts: list[str] = []
    await _run_prompt_turn(
        session,
        websocket,
        content,
        turn_config,
        pending_prompts,
        sessions,
        prompt_registry,
        # Passed explicitly (rather than letting the helpers import it from
        # here) so tests that monkeypatch ``chat.stream_prompt`` keep working
        # without an import cycle (issue #110).
        stream_fn=stream_prompt,
        steering_prompts=steering_prompts,
    )
    while steering_prompts or pending_prompts:
        mode = "steer" if steering_prompts else "queue"
        extra = (steering_prompts if steering_prompts else pending_prompts).pop(0)
        _maybe_auto_title(sessions, session.session_id, session, extra)
        await websocket.send_json(PromptStartedEvent(content=extra, mode=mode).to_dict())
        await _run_prompt_turn(
            session,
            websocket,
            extra,
            turn_config,
            pending_prompts,
            sessions,
            prompt_registry,
            stream_fn=stream_prompt,
            steering_prompts=steering_prompts,
        )


async def _dispatch_client_message(
    websocket: WebSocket,
    session: ConversationSession,
    session_id: str,
    sessions: SessionManager,
    config,
    prompt_registry: PromptRegistry,
    msg: dict,
) -> None:
    """Handle one client frame from the chat WebSocket.

    ``restart`` clears the session; ``prompt_answer`` resolves an in-browser
    question (AskUser tool) posted while the connection is idle (e.g. right
    as the turn finished); ``prompt`` runs a full turn, draining any prompts
    queued meanwhile. Unknown message types (e.g. pings) are ignored.
    """
    msg_type = msg.get("type")
    if msg_type == "restart":
        await _handle_restart(session, sessions, session_id, websocket)
        return
    if msg_type == "prompt_answer":
        # An answer posted as the turn finished (e.g. the user hit Submit
        # right as the stream ended). Resolving an unknown id is a harmless
        # no-op.
        prompt_registry.resolve(msg.get("prompt_id", ""), msg.get("answer", ""))
        return
    if msg_type != "prompt":
        return  # ignore unknown message types (could be pings)

    content = (msg.get("content") or "").strip()
    if not content:
        await websocket.send_json({"type": "error", "message": "Empty prompt"})
        return

    pending_prompts: list[str] = []
    # A busy submission may reach the server just after the previous turn
    # finished. It still needs an acknowledgement to start its browser row.
    if msg.get("mode") in {"steer", "queue"}:
        await websocket.send_json(PromptStartedEvent(content=content, mode=msg["mode"]).to_dict())
    await _process_prompt(
        session,
        websocket,
        config,
        content,
        pending_prompts,
        sessions,
        prompt_registry,
    )


@router.websocket("/ws/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """Bidirectional streaming chat over WebSocket.

    Protocol (JSON messages):
      Client -> Server:  {"type": "prompt"|"restart"|"cancel"|
                                "prompt_answer", ...}
      Server -> Client:  {"type": "token"|"reasoning"|"tool_call"|
                                "prompt"|...}
    """
    session = await _accept_session(websocket, session_id)
    if session is None:
        return

    await _send_session_greeting(websocket)

    sessions: SessionManager = websocket.app.state.sessions
    config = websocket.app.state.config

    # Tracks questions raised by interactive tools (AskUser) for this
    # connection, answered by the browser via ``prompt_answer`` frames.
    prompt_registry = PromptRegistry()

    try:
        while True:
            msg = await _read_client_message(websocket)
            if msg is None:  # disconnect
                break
            await _dispatch_client_message(websocket, session, session_id, sessions, config, prompt_registry, msg)
    except WebSocketDisconnect:
        logger.debug(f"WebSocket client disconnected: {session_id}")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass


# ---------------------------------------------------------------------------
# One-shot SSE endpoint (alternative to the WebSocket)
# ---------------------------------------------------------------------------


@router.post("/prompt")
async def one_shot_prompt(request: Request):
    """One-shot Server-Sent-Events streaming endpoint (alternative to WS).

    Body: {"session_id": "...", "content": "..."}
    Returns an ``text/event-stream`` response.
    """
    from fastapi.responses import StreamingResponse

    sessions = _get_sessions(request)
    config = _get_config(request)

    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)

    session_id = body.get("session_id")
    content = (body.get("content") or "").strip()
    if not session_id or not content:
        return JSONResponse({"detail": "session_id and content are required"}, status_code=400)

    session = sessions.get(session_id)
    if not session:
        return JSONResponse({"detail": "Session not found"}, status_code=404)

    session.touch()  # sending a prompt is activity (TTL reaping, issue #93)
    if session.provider is None:
        session.provider = config.effective_provider
        session.model = config.model or load_model_from_config(session.provider)
        if not session.model:
            found = get_provider(session.provider)
            session.model = found.default_model() if found is not None else None
        sessions.persist(session)
    turn_config = copy.copy(config)
    turn_config.provider = session.provider
    turn_config.session_provider = session.provider
    turn_config.model = session.model

    async def sse():
        try:
            async for event in stream_prompt(content, session.messages, turn_config):
                payload = json.dumps(event_to_dict(event))
                yield f"data: {payload}\n\n"
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Persist whatever the turn left in the conversation (success or
            # error) so the one-shot path keeps sessions on disk too.
            sessions.persist(session)

    return StreamingResponse(sse(), media_type="text/event-stream")
