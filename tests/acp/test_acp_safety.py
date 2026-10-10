"""Regression tests for ACP turn safety: cwd ownership, cancel drain, rollback."""

from __future__ import annotations

import asyncio
import os
import time

from janito.acp.agent import AcpSession, JanitoAgent
from janito.acp.protocol import INVALID_PARAMS, RpcError
from janito.web.backend.agent.workers import run_in_worker
from janito.web.backend.config import WebServerConfig
from janito.web.backend.events import DoneEvent, ErrorEvent, TokenEvent, ToolCallEvent, ToolResultEvent


class CollectWriter:
    def __init__(self):
        self.messages = []

    async def write(self, payload):
        self.messages.append(payload)


def make_agent(turn_runner=None, writer=None, config=None) -> JanitoAgent:
    config = config or WebServerConfig(system_prompt="test-system")
    return JanitoAgent(config, turn_runner=turn_runner, writer=writer or CollectWriter())


def test_worker_thread_sees_session_cwd_and_cwd_restored(tmp_path):
    """Tracked sync work runs under the session cwd; cwd restored after."""
    original_cwd = os.getcwd()
    session_cwd = str(tmp_path)
    seen: dict = {}

    async def cwd_runner(prompt, messages, config, **kwargs):
        messages.append({"role": "user", "content": prompt})

        def _read_cwd():
            time.sleep(0.05)
            return os.getcwd()

        seen["worker_cwd"] = await run_in_worker(_read_cwd)
        yield TokenEvent(content="done")
        messages.append({"role": "assistant", "content": "done"})

    agent = make_agent(turn_runner=cwd_runner)
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=session_cwd)
    result = asyncio.run(
        agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "hi"}]})
    )
    assert result == {"stopReason": "end_turn"}
    assert os.path.abspath(seen["worker_cwd"]) == os.path.abspath(session_cwd)
    assert os.getcwd() == original_cwd


def test_repeated_cancel_drains_worker_and_restores_cwd(tmp_path):
    """Two cancels still resolve as cancelled with cwd restored and history rolled back."""
    original_cwd = os.getcwd()
    session_cwd = str(tmp_path)
    seen: dict = {}

    async def slow_runner(prompt, messages, config, **kwargs):
        messages.append({"role": "user", "content": prompt})

        def _slow():
            time.sleep(0.3)
            seen["worker_cwd"] = os.getcwd()
            return seen["worker_cwd"]

        await run_in_worker(_slow)
        yield TokenEvent(content="late")
        messages.append({"role": "assistant", "content": "late"})

    agent = make_agent(turn_runner=slow_runner)
    agent._sessions["s1"] = AcpSession(
        session_id="s1", cwd=session_cwd, messages=[{"role": "system", "content": "sys"}]
    )

    async def scenario():
        task = asyncio.create_task(
            agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "go"}]})
        )
        await asyncio.sleep(0.05)
        agent._cancel({"sessionId": "s1"})
        await asyncio.sleep(0.01)
        agent._cancel({"sessionId": "s1"})
        return await task

    assert asyncio.run(scenario()) == {"stopReason": "cancelled"}
    assert os.getcwd() == original_cwd
    # Worker finished before cwd restore, so it saw the session cwd.
    assert os.path.abspath(seen["worker_cwd"]) == os.path.abspath(session_cwd)
    # History rolled back to the pre-turn system message.
    assert agent._sessions["s1"].messages == [{"role": "system", "content": "sys"}]


def test_error_event_rolls_back_tool_call_history():
    """A turn ending in ErrorEvent drops its user/tool messages, keeps system."""

    async def failing_runner(prompt, messages, config, **kwargs):
        messages.append({"role": "user", "content": prompt})
        tool_calls = [{"id": "call_1", "type": "function", "function": {"name": "ReadFile", "arguments": "{}"}}]
        messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
        messages.append({"role": "tool", "tool_call_id": "call_1", "name": "ReadFile", "content": "x"})
        yield ToolCallEvent(tool_call_id="call_1", tool_name="ReadFile", arguments={})
        yield ToolResultEvent(tool_call_id="call_1", tool_name="ReadFile", result="x", error=None)
        yield ErrorEvent(message="boom")

    agent = make_agent(turn_runner=failing_runner)
    agent._sessions["s1"] = AcpSession(
        session_id="s1", cwd=os.getcwd(), messages=[{"role": "system", "content": "sys"}]
    )
    result = asyncio.run(
        agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "hi"}]})
    )
    assert result == {"stopReason": "end_turn"}
    assert agent._sessions["s1"].messages == [{"role": "system", "content": "sys"}]


def test_exception_rolls_back_but_completed_history_survives():
    """A failed second turn preserves the first completed turn's history."""
    calls = {"n": 0}

    async def runner(prompt, messages, config, **kwargs):
        calls["n"] += 1
        messages.append({"role": "user", "content": prompt})
        if calls["n"] == 2:
            raise RuntimeError("mid-turn failure")
        yield TokenEvent(content="ok")
        messages.append({"role": "assistant", "content": "ok"})
        yield DoneEvent(full_content="ok", message_count=len(messages))

    agent = make_agent(turn_runner=runner)
    agent._sessions["s1"] = AcpSession(
        session_id="s1", cwd=os.getcwd(), messages=[{"role": "system", "content": "sys"}]
    )
    first = asyncio.run(
        agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "one"}]})
    )
    assert first == {"stopReason": "end_turn"}
    after_first = list(agent._sessions["s1"].messages)
    assert len(after_first) == 3  # system + user + assistant

    second = asyncio.run(
        agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "two"}]})
    )
    assert second == {"stopReason": "end_turn"}
    assert agent._sessions["s1"].messages == after_first


def test_same_session_overlapping_prompt_rejected():
    """Overlapping prompts on one session raise instead of interleaving."""
    release = asyncio.Event()

    async def gated(prompt, messages, config, **kwargs):
        messages.append({"role": "user", "content": prompt})
        await release.wait()
        yield TokenEvent(content="done")

    agent = make_agent(turn_runner=gated)
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=os.getcwd())

    async def scenario():
        first = asyncio.create_task(
            agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "one"}]})
        )
        await asyncio.sleep(0.05)
        import pytest as _pytest

        with _pytest.raises(RpcError) as exc:
            await agent.handle_request(
                "session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "two"}]}
            )
        assert exc.value.code == INVALID_PARAMS
        release.set()
        assert await first == {"stopReason": "end_turn"}

    asyncio.run(scenario())


def test_new_session_resolves_distinct_agents_md(tmp_path):
    """Each session/new picks up the AGENTS.md of its own cwd."""
    dir_a = tmp_path / "proj-a"
    dir_b = tmp_path / "proj-b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "AGENTS.md").write_text("alpha-marker-123\n", encoding="utf-8")
    (dir_b / "AGENTS.md").write_text("beta-marker-456\n", encoding="utf-8")

    agent = make_agent(config=WebServerConfig())

    async def scenario():
        res_a = await agent.handle_request("session/new", {"cwd": str(dir_a)})
        res_b = await agent.handle_request("session/new", {"cwd": str(dir_b)})
        return res_a, res_b

    res_a, res_b = asyncio.run(scenario())
    sys_a = agent._sessions[res_a["sessionId"]].messages[0]["content"]
    sys_b = agent._sessions[res_b["sessionId"]].messages[0]["content"]
    assert "alpha-marker-123" in sys_a
    assert "beta-marker-456" not in sys_a
    assert "beta-marker-456" in sys_b
    assert "alpha-marker-123" not in sys_b


def test_new_session_waits_for_active_turn(tmp_path):
    """session/new blocks on the turn lock instead of racing the active cwd."""
    project_a = tmp_path / "active"
    project_b = tmp_path / "new"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "AGENTS.md").write_text("active-project-marker", encoding="utf-8")
    (project_b / "AGENTS.md").write_text("new-project-marker", encoding="utf-8")
    started = asyncio.Event()
    release = asyncio.Event()

    async def gated(prompt, messages, config, **kwargs):
        messages.append({"role": "user", "content": prompt})
        started.set()
        await release.wait()
        yield TokenEvent(content="done")
        messages.append({"role": "assistant", "content": "done"})

    agent = make_agent(turn_runner=gated, config=WebServerConfig())
    agent._sessions["s1"] = AcpSession(session_id="s1", cwd=str(project_a))

    async def scenario():
        first = asyncio.create_task(
            agent.handle_request("session/prompt", {"sessionId": "s1", "prompt": [{"type": "text", "text": "one"}]})
        )
        await started.wait()
        new_task = asyncio.create_task(agent.handle_request("session/new", {"cwd": str(project_b)}))
        await asyncio.sleep(0.05)
        assert not new_task.done()
        release.set()
        assert await first == {"stopReason": "end_turn"}
        result = await new_task
        content = agent._sessions[result["sessionId"]].messages[0]["content"]
        assert "new-project-marker" in content
        assert "active-project-marker" not in content

    asyncio.run(scenario())
