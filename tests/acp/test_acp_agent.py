"""Unit tests for the ACP agent (JanitoAgent protocol handlers)."""

from __future__ import annotations

import asyncio
import os

import pytest

from janito.acp.agent import AcpSession, JanitoAgent, blocks_to_text
from janito.acp.protocol import INVALID_PARAMS, METHOD_NOT_FOUND, RpcError
from janito.web.backend.config import WebServerConfig
from janito.web.backend.events import (
    DoneEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    WaitingEvent,
)

SYSTEM_PROMPT = "You are a test agent."


class CollectWriter:
    def __init__(self):
        self.messages = []

    async def write(self, payload):
        self.messages.append(payload)


def make_agent(turn_runner=None, writer=None) -> JanitoAgent:
    config = WebServerConfig(system_prompt=SYSTEM_PROMPT)
    return JanitoAgent(config, turn_runner=turn_runner, writer=writer)


def _run(coro):
    return asyncio.run(coro)


def test_initialize_negotiates_v1():
    agent = make_agent()
    result = _run(agent.handle_request("initialize", {"protocolVersion": 1}))
    assert result["protocolVersion"] == 1
    assert result["agentInfo"]["name"] == "janito"
    assert result["agentInfo"]["version"]
    assert result["authMethods"] == []
    caps = result["agentCapabilities"]
    assert caps["loadSession"] is False
    assert caps["promptCapabilities"] == {"image": False, "audio": False, "embeddedContext": True}
    assert caps["mcpCapabilities"] == {"http": False, "sse": False}


def test_unknown_method_raises_method_not_found():
    agent = make_agent()
    with pytest.raises(RpcError) as exc:
        _run(agent.handle_request("session/load", {}))
    assert exc.value.code == METHOD_NOT_FOUND


def test_new_session_requires_absolute_cwd():
    agent = make_agent()
    with pytest.raises(RpcError) as exc:
        _run(agent.handle_request("session/new", {}))
    assert exc.value.code == INVALID_PARAMS
    with pytest.raises(RpcError):
        _run(agent.handle_request("session/new", {"cwd": "relative/dir"}))
    with pytest.raises(RpcError):
        _run(agent.handle_request("session/new", {"cwd": 42}))


def test_new_session_ignores_client_mcp_servers(caplog):
    agent = make_agent()
    result = _run(
        agent.handle_request("session/new", {"cwd": os.getcwd(), "mcpServers": [{"name": "nope", "url": "http://x"}]})
    )
    session = agent._sessions[result["sessionId"]]
    assert session.cwd == os.getcwd()
    assert session.messages == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert any("ignores" in record.message or "ignores" in record.getMessage() for record in caplog.records)


async def _fake_turn(prompt, messages, config, **kwargs):
    messages.append({"role": "user", "content": prompt})
    yield TokenEvent(content="Hello ")
    yield ToolCallEvent(tool_call_id="call_1", tool_name="ReadFile", arguments={"filepath": "a.txt"})
    yield ToolResultEvent(
        tool_call_id="call_1",
        tool_name="ReadFile",
        result={"success": True, "content": "x"},
        error=None,
    )
    yield TokenEvent(content="world")
    yield DoneEvent(full_content="Hello world", message_count=2)
    messages.append({"role": "assistant", "content": "Hello world"})


def test_prompt_streams_updates_and_restores_cwd(tmp_path, monkeypatch):
    original_cwd = os.getcwd()
    session_cwd = str(tmp_path)
    writer = CollectWriter()
    agent = make_agent(turn_runner=_fake_turn, writer=writer)
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=session_cwd)

    result = _run(
        agent.handle_request(
            "session/prompt",
            {
                "sessionId": "s1",
                "prompt": [{"type": "text", "text": "hi"}, {"type": "resource_link", "uri": "file:///x.txt"}],
            },
        )
    )
    assert result == {"stopReason": "end_turn"}

    updates = [m["params"]["update"] for m in writer.messages if m["method"] == "session/update"]
    assert [u["sessionUpdate"] for u in updates] == [
        "agent_message_chunk",
        "tool_call",
        "tool_call_update",
        "agent_message_chunk",
    ]
    asserted = updates[1]
    assert asserted["title"] == "Reading file"
    assert asserted["kind"] == "read"
    assert asserted["locations"] == [{"path": os.path.abspath(os.path.join(session_cwd, "a.txt"))}]

    # The turn runner saw the appended user message and the history persisted.
    # (The session was created directly, so there is no system message.)
    session = agent._sessions["s1"]
    assert session.messages[0] == {"role": "user", "content": "hi\n\n[Referenced file: file:///x.txt]"}
    assert session.messages[1]["role"] == "assistant"

    assert os.getcwd() == original_cwd


def test_prompt_unknown_session_raises():
    agent = make_agent()
    with pytest.raises(RpcError) as exc:
        _run(agent.handle_request("session/prompt", {"sessionId": "ghost", "prompt": [{"type": "text", "text": "hi"}]}))
    assert exc.value.code == INVALID_PARAMS


def test_prompt_rejects_non_list_prompt():
    agent = make_agent()
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=os.getcwd())
    with pytest.raises(RpcError):
        _run(agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": "hi"}))


async def _never_runner(prompt, messages, config, **kwargs):
    messages.append({"role": "user", "content": prompt})
    yield WaitingEvent(phase="initial")
    await asyncio.sleep(3600)


async def _gated_runner(release, prompt, messages, config, **kwargs):
    messages.append({"role": "user", "content": prompt})
    await release.wait()
    yield TokenEvent(content="gated done")


def test_overlapping_prompt_same_session_rejected():
    """A second prompt on a session with a running turn is rejected."""
    release_first = asyncio.Event()
    agent = make_agent(turn_runner=lambda *a, **k: _gated_runner(release_first, *a, **k))
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=os.getcwd())

    async def scenario():
        first = asyncio.create_task(
            agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "one"}]})
        )
        await asyncio.sleep(0.05)
        with pytest.raises(RpcError) as exc:
            await agent.handle_request(
                "session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "two"}]}
            )
        assert exc.value.code == INVALID_PARAMS
        release_first.set()
        assert await first == {"stopReason": "end_turn"}

    asyncio.run(scenario())


def test_prompt_cancellation_returns_cancelled_stop():
    agent = make_agent(turn_runner=_never_runner)
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=os.getcwd())

    async def scenario():
        task = asyncio.create_task(
            agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "go"}]})
        )
        await asyncio.sleep(0)
        agent._cancel({"sessionId": "s1"})
        return await task

    assert asyncio.run(scenario()) == {"stopReason": "cancelled"}


def test_blocks_to_text():
    text = blocks_to_text(
        [
            {"type": "text", "text": "  Hello  "},
            {"type": "resource", "resource": {"uri": "file:///a.txt", "text": "file contents"}},
            {"type": "resource_link", "uri": "file:///b.txt"},
            {"type": "image", "image": {"data": "..."}},
            {"type": "audio", "audio": {"data": "..."}},
        ]
    )
    assert "Hello" in text
    assert "file contents" in text
    assert "[source: file:///a.txt]" in text
    assert "[Referenced file: file:///b.txt]" in text
    assert "ignored" in text


def test_blocks_to_text_empty():
    assert blocks_to_text([]) == ""
    assert blocks_to_text(None) == ""
    text = blocks_to_text([{"type": "image", "image": {}}])
    assert text != ""
    assert "ignored" in text


def test_acp_cli_flag():
    from janito.cli.parser import create_parser

    args = create_parser().parse_args(["--acp"])
    assert args.acp is True
    args = create_parser().parse_args([])
    assert args.acp is False
