"""Contract tests for reliable message submission in the web chat.

The web input box used to silently swallow submissions in several
situations: pressing Enter while a response was in flight (waiting /
streaming / tool_running) returned early and left the typed text in the
box with no feedback, and a submission made while the active session was
missing (page still bootstrapping, or the conversation just deleted) was
dropped the same way. A failed socket send also cleared the input *before*
the message was handed to the server, losing the typed text.

These tests pin down:

1. ``_await_cancel`` (backend) queues prompts that arrive mid-turn instead
   of discarding them, so the main loop can process them afterwards.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

# The web routes need the optional `web` extra (fastapi). Skip gracefully
# when fastapi is not installed (e.g. minimal tox envs).
try:
    import fastapi  # noqa: F401
    from fastapi import WebSocketDisconnect

    _HAS_FASTAPI = True
except ModuleNotFoundError:
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi (web extra) is not installed")


# ---------------------------------------------------------------------------
# Backend: mid-turn prompts are queued, not discarded
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Minimal stand-in with a canned receive_text() feed."""

    def __init__(self, frames):
        self._frames = list(frames)

    async def receive_text(self):
        if not self._frames:
            raise WebSocketDisconnect()
        return self._frames.pop(0)


@requires_fastapi
def test_await_cancel_queues_mid_turn_prompts():
    """Prompts arriving during a turn are queued, then cancel returns True."""
    from janito.web.backend.routers.chat_helpers import _await_cancel

    ws = _FakeWebSocket(
        [
            json.dumps({"type": "prompt", "content": "first"}),
            json.dumps({"type": "prompt", "content": "  second  "}),
            json.dumps({"type": "cancel"}),
        ]
    )
    pending: list[str] = []
    result = asyncio.run(_await_cancel(ws, pending))

    assert result is True
    # Both prompts were preserved (whitespace-trimmed) for the main loop.
    assert pending == ["first", "second"]


@requires_fastapi
def test_await_cancel_skips_empty_prompts():
    """Blank prompts are not queued (they would be rejected anyway)."""
    from janito.web.backend.routers.chat_helpers import _await_cancel

    ws = _FakeWebSocket(
        [
            json.dumps({"type": "prompt", "content": "   "}),
            json.dumps({"type": "prompt", "content": "ok"}),
            json.dumps({"type": "cancel"}),
        ]
    )
    pending: list[str] = []
    result = asyncio.run(_await_cancel(ws, pending))

    assert result is True
    assert pending == ["ok"]


@requires_fastapi
def test_await_cancel_returns_false_on_disconnect():
    """A disconnect (no cancel) reports False so the caller stops."""
    from janito.web.backend.routers.chat_helpers import _await_cancel

    ws = _FakeWebSocket([])
    result = asyncio.run(_await_cancel(ws, []))
    assert result is False


@requires_fastapi
def test_await_cancel_ignores_unknown_message_types():
    """Pings/unknown frames are ignored without losing queued prompts."""
    from janito.web.backend.routers.chat_helpers import _await_cancel

    ws = _FakeWebSocket(
        [
            json.dumps({"type": "ping"}),
            json.dumps({"type": "prompt", "content": "hello"}),
            json.dumps({"type": "cancel"}),
        ]
    )
    pending: list[str] = []
    result = asyncio.run(_await_cancel(ws, pending))

    assert result is True
    assert pending == ["hello"]


@requires_fastapi
def test_await_cancel_routes_steering_separately_from_fifo_followups():
    from janito.web.backend.routers.chat_helpers import _await_cancel

    ws = _FakeWebSocket(
        [
            json.dumps({"type": "prompt", "mode": "queue", "content": "later"}),
            json.dumps({"type": "prompt", "mode": "steer", "content": "  next step  "}),
            json.dumps({"type": "prompt", "mode": "steer", "content": " "}),
            json.dumps({"type": "prompt", "content": "another followup"}),
            json.dumps({"type": "cancel"}),
        ]
    )
    pending, steering = [], []
    assert asyncio.run(_await_cancel(ws, pending, steering_prompts=steering)) is True
    assert pending == ["later", "another followup"]
    assert steering == ["next step"]
