"""Exercise cancellation through the real tool thread hop and server shutdown."""

import asyncio
import os
import threading

from janito.acp.agent import AcpSession, JanitoAgent
from janito.acp.server import JsonRpcServer
from janito.web.backend.agent import tooling
from janito.web.backend.agent.turn import run_tool_turn
from janito.web.backend.agent.workers import WorkerTracker, drain_shielded, reset_tracker, run_in_worker, set_tracker
from janito.web.backend.config import WebServerConfig
from janito.web.backend.events import TokenEvent


class CaptureWriter:
    def __init__(self):
        self.messages = []

    async def write(self, payload):
        self.messages.append(payload)


def prompt(session_id):
    return {"sessionId": session_id, "prompt": [{"type": "text", "text": "read project"}]}


def test_cancelled_tool_finishes_before_next_project_turn(tmp_path, monkeypatch):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "marker.txt").write_text("a", encoding="utf-8")
    (project_b / "marker.txt").write_text("b", encoding="utf-8")
    started = threading.Event()
    release = threading.Event()
    observed = []
    original_cwd = os.getcwd()

    def gated_tool(*args, **kwargs):
        started.set()
        assert release.wait(5), "test did not release worker"
        with open("marker.txt", encoding="utf-8") as file:
            observed.append(file.read())
        return {"success": True}, None, 1

    monkeypatch.setattr(tooling, "run_tool", gated_tool)

    async def runner(text, messages, config):
        messages.append({"role": "user", "content": text})
        if os.getcwd() == str(project_a):
            calls = [{"id": "read1", "type": "function",
                      "function": {"name": "ReadFile", "arguments": '{"filepath":"marker.txt"}'}}]
            async for event in run_tool_turn(calls, "", messages, False, allowed_tools={"ReadFile"}):
                yield event
        else:
            observed.append("next:" + os.getcwd())
            yield TokenEvent(content="complete")
            messages.append({"role": "assistant", "content": "complete"})

    agent = JanitoAgent(WebServerConfig(), turn_runner=runner, writer=CaptureWriter())
    saved_history = [{"role": "system", "content": "instructions"}]
    agent._sessions["a"] = AcpSession("a", str(project_a), list(saved_history))
    agent._sessions["b"] = AcpSession("b", str(project_b))

    async def scenario():
        first = asyncio.create_task(agent.handle_request("session/prompt", prompt("a")))
        second = None
        try:
            assert await asyncio.to_thread(started.wait, 5)
            agent._cancel({"sessionId": "a"})
            second = asyncio.create_task(agent.handle_request("session/prompt", prompt("b")))
            await asyncio.sleep(0)
            agent._cancel({"sessionId": "a"})
            await asyncio.sleep(0)
            assert not first.done()
            assert not second.done()
            assert os.getcwd() == str(project_a)
        finally:
            release.set()
            results = await asyncio.gather(first, *([second] if second else []))
        assert results == [{"stopReason": "cancelled"}, {"stopReason": "end_turn"}]

    asyncio.run(scenario())
    assert observed == ["a", "next:" + str(project_b)]
    assert agent._sessions["a"].messages == saved_history
    assert not agent._running
    assert os.getcwd() == original_cwd


def test_stdio_eof_waits_for_turn_cleanup(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    eof_reached = asyncio.Event()
    original_cwd = os.getcwd()
    observed = []

    def worker():
        started.set()
        assert release.wait(5), "test did not release worker"
        observed.append(os.getcwd())

    async def runner(text, messages, config):
        messages.append({"role": "user", "content": text})
        await run_in_worker(worker)
        yield TokenEvent(content="done")

    agent = JanitoAgent(WebServerConfig(), turn_runner=runner)
    agent._sessions["s"] = AcpSession("s", str(tmp_path))
    writer = CaptureWriter()
    server = JsonRpcServer(agent, writer)

    async def incoming():
        yield {"jsonrpc": "2.0", "id": 1, "method": "session/prompt", "params": prompt("s")}
        assert await asyncio.to_thread(started.wait, 5)
        eof_reached.set()
        # Returning simulates stdin EOF, without invoking platform-specific pipes.

    monkeypatch.setattr("janito.acp.server._iter_stdin_messages", incoming)

    async def scenario():
        serving = asyncio.create_task(server.serve_stdio())
        try:
            await asyncio.wait_for(eof_reached.wait(), 5)
            await asyncio.sleep(0)
            assert not serving.done()
            assert os.getcwd() == str(tmp_path)
        finally:
            release.set()
            await serving

    asyncio.run(scenario())
    assert observed == [str(tmp_path)]
    assert os.getcwd() == original_cwd
    assert agent._sessions["s"].messages == []
    assert writer.messages[-1]["result"] == {"stopReason": "cancelled"}


def test_cancelled_worker_exception_is_consumed():
    started = threading.Event()
    release = threading.Event()
    errors = []

    def failing_worker():
        started.set()
        assert release.wait(5), "test did not release worker"
        raise ValueError("worker failed after caller cancelled")

    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda loop, context: errors.append(context))
        tracker = WorkerTracker()
        token = set_tracker(tracker)
        try:
            task = asyncio.create_task(run_in_worker(failing_worker))
            try:
                assert await asyncio.to_thread(started.wait, 5)
                task.cancel()
                result = await asyncio.gather(task, return_exceptions=True)
                assert isinstance(result[0], asyncio.CancelledError)
            finally:
                release.set()
                await drain_shielded(tracker)
            await asyncio.sleep(0)
        finally:
            reset_tracker(token)

    asyncio.run(scenario())
    assert errors == []
