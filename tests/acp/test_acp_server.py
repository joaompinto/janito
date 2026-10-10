"""Unit tests for the ACP JSON-RPC stdio server."""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys

from janito.acp.agent import JanitoAgent
from janito.acp.protocol import INVALID_PARAMS, INTERNAL_ERROR, METHOD_NOT_FOUND, compact_json
from janito.acp.server import JsonRpcServer, StdioWriter
from janito.web.backend.config import WebServerConfig
from janito.web.backend.events import WaitingEvent


class _CaptureWriter:
    def __init__(self):
        self.messages = []

    async def write(self, payload):
        self.messages.append(payload)


def _make_server(writer=None) -> JsonRpcServer:
    config = WebServerConfig(system_prompt="test")
    return JsonRpcServer(JanitoAgent(config), writer=writer)


def _make_capture_server() -> JsonRpcServer:
    return _make_server(writer=_CaptureWriter())


def _process(server, *messages):
    """Deliver messages to the server and drain in-flight tasks."""

    async def run():
        for message in messages:
            await server._on_message(message)
        await asyncio.gather(*list(server._tasks), return_exceptions=True)

    asyncio.run(run())


def test_compact_json_has_no_embedded_newlines():
    text = compact_json({"message": "line1\nline2", "nested": {"a": [1, 2]}})
    assert "\n" not in text
    assert json.loads(text)["message"] == "line1\nline2"


def test_initialize_roundtrip():
    server = _make_capture_server()
    _process(server, {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {"protocolVersion": 1}})
    payload = server._writer.messages[0]
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 7
    assert payload["result"]["protocolVersion"] == 1


def test_unknown_method_error():
    server = _make_capture_server()
    _process(server, {"jsonrpc": "2.0", "id": 2, "method": "session/load", "params": {}})
    payload = server._writer.messages[0]
    assert payload["error"] == {"code": METHOD_NOT_FOUND, "message": "Method not found: session/load"}


def test_handler_rpc_error_becomes_error_response():
    server = _make_capture_server()
    _process(server, {"jsonrpc": "2.0", "id": 3, "method": "session/new", "params": {}})  # missing cwd
    payload = server._writer.messages[0]
    assert payload["error"]["code"] == INVALID_PARAMS


def test_unexpected_error_becomes_internal_error(monkeypatch):
    server = _make_capture_server()

    async def boom(method, params):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(server.agent, "handle_request", boom)
    _process(server, {"jsonrpc": "2.0", "id": 4, "method": "anything", "params": {}})
    payload = server._writer.messages[0]
    assert payload["error"]["code"] == INTERNAL_ERROR
    assert "kaboom" in payload["error"]["message"]


def test_notification_is_not_answered():
    server = _make_capture_server()
    _process(server, {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "x"}})
    assert server._writer.messages == []


def test_request_without_method_is_invalid_request():
    server = _make_capture_server()
    _process(server, {"jsonrpc": "2.0", "id": 9})
    payload = server._writer.messages[0]
    assert payload["id"] == 9
    assert payload["error"]["code"] == -32600


def test_non_object_params_are_rejected():
    server = _make_capture_server()
    _process(server, {"jsonrpc": "2.0", "id": 10, "method": "session/new", "params": "cwd"})
    payload = server._writer.messages[0]
    assert payload["error"]["code"] == INVALID_PARAMS


def test_editor_handshake_end_to_end(monkeypatch):
    """Feed the messages an ACP client sends at startup and check stdout."""
    outgoing = io.StringIO()
    monkeypatch.setattr(sys, "stdout", outgoing)

    server = _make_server(writer=StdioWriter())

    _process(
        server,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}},
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": os.getcwd(), "mcpServers": []}},
        {"jsonrpc": "2.0", "id": 3, "method": "does.not.exist", "params": {}},
    )

    lines = [line for line in outgoing.getvalue().splitlines() if line]
    assert len(lines) == 3
    responses = [json.loads(line) for line in lines]
    assert len(responses) == 3
    assert responses[0]["id"] == 1 and "protocolVersion" in responses[0]["result"]
    assert "sessionId" in responses[1]["result"]
    assert responses[2]["error"]["code"] == METHOD_NOT_FOUND


async def _slow_turn(prompt, messages, config, **kwargs):
    messages.append({"role": "user", "content": prompt})
    yield WaitingEvent(phase="initial")
    await asyncio.sleep(3600)


def test_cancel_notification_cancels_running_prompt():
    """session/cancel through the transport resolves the prompt as cancelled."""
    config = WebServerConfig(system_prompt="test")
    agent = JanitoAgent(config, turn_runner=_slow_turn)
    server = JsonRpcServer(agent, writer=_CaptureWriter())

    async def run():
        await server._on_message(
            {"jsonrpc": "2.0", "id": 5, "method": "session/new", "params": {"cwd": os.getcwd()}}
        )
        await asyncio.sleep(0)
        session_id = server._writer.messages[0]["result"]["sessionId"]
        await server._on_message(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "session/prompt",
                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "go"}]},
            }
        )
        await asyncio.sleep(0.05)
        await server._on_message({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
        await asyncio.gather(*list(server._tasks), return_exceptions=True)

    asyncio.run(run())

    responses = {message["id"]: message for message in server._writer.messages if "id" in message}
    assert responses[6]["result"] == {"stopReason": "cancelled"}
