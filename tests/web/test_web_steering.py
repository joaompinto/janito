"""Steering is applied at safe boundaries; follow-ups remain FIFO turns."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("fastapi")

from janito.web.backend.agent import loop
from janito.web.backend.config import WebServerConfig
from janito.web.backend.events import DoneEvent, ErrorEvent, TokenEvent, ToolResultEvent
from janito.web.backend.routers import chat, chat_helpers
from janito.web.backend.session import ConversationSession


@pytest.mark.parametrize("arrival", ["before_model", "during_model", "during_tool"])
def test_steer_reaches_next_model_round_without_breaking_tool_history(monkeypatch, arrival):
    steering = ["adjust"] if arrival == "before_model" else []
    calls = []
    messages = []
    tool_call = {"id": "tc1", "type": "function", "function": {"name": "Read", "arguments": "{}"}}
    monkeypatch.setattr(loop, "resolve_runtime_config", lambda **kwargs: (None, "test-key", "test-model"))
    monkeypatch.setattr(loop, "_create_agent_client", lambda *args: object())
    monkeypatch.setattr(loop, "_resolve_turn_config", lambda *args: (1000, False, None))
    monkeypatch.setattr(loop, "resolve_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(loop, "reset_used_files", lambda: None)
    monkeypatch.setattr(loop, "_record_web_turn", lambda *args: None)

    def build_round(*args):
        calls.append([dict(message) for message in messages])
        tool_calls = [tool_call] if arrival == "during_tool" and len(calls) == 1 else []
        acc = SimpleNamespace(
            full_content=lambda: f"round {len(calls)}",
            reasoning_content=lambda: "",
            usage_object=lambda: None,
            tool_calls_list=lambda: tool_calls,
        )
        return {}, acc

    async def stream_round(*args):
        yield TokenEvent(content="response")
        if arrival == "during_model" and len(calls) == 1:
            steering.extend(["adjust", "and keep tests"])

    async def tool_round(tool_calls, content, history, *args, **kwargs):
        history.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        steering.append("adjust")  # received while the tool is still running
        history.append({"role": "tool", "tool_call_id": "tc1", "content": "result"})
        yield ToolResultEvent(tool_call_id="tc1", tool_name="Read", result="result")

    monkeypatch.setattr(loop, "_turn_call_kwargs_and_acc", build_round)
    monkeypatch.setattr(loop, "_stream_turn", stream_round)
    monkeypatch.setattr(loop, "run_tool_turn", tool_round)

    async def run():
        config = WebServerConfig(provider="openai", api_type="Completions", no_tools=True)
        return [event async for event in loop.stream_prompt("original", messages, config, steering_prompts=steering)]

    events = asyncio.run(run())
    assert steering == []
    assert len(calls) == (1 if arrival == "before_model" else 2)
    applied = [event.content for event in events if event.type == "prompt_started"]
    assert applied == (["adjust", "and keep tests"] if arrival == "during_model" else ["adjust"])
    assert calls[-1][-1] == {"role": "user", "content": applied[-1]}
    assert sum(event.type == "done" for event in events) == 1
    assert isinstance(events[-1], DoneEvent)
    if arrival == "during_tool":
        assert [message["role"] for message in calls[-1]] == ["user", "assistant", "tool", "user"]
        result_index = next(i for i, event in enumerate(events) if event.type == "tool_result")
        steer_index = next(i for i, event in enumerate(events) if event.type == "prompt_started")
        assert result_index < steer_index


def test_followups_are_drained_once_in_fifo_order_after_steering(monkeypatch):
    seen = []
    sent = []

    async def turn(session, websocket, content, config, pending, sessions, registry, **kwargs):
        seen.append(content)
        if content == "original":
            pending.extend(["queue one", "queue two"])
            kwargs["steering_prompts"].append("late steer")
        elif content == "queue one":
            pending.append("queue three")

    monkeypatch.setattr(chat, "_run_prompt_turn", turn)
    session = ConversationSession(session_id="s1", provider="openai", model="test", title="Existing")
    ws = SimpleNamespace(send_json=AsyncMock(side_effect=sent.append))
    pending = []
    asyncio.run(chat._process_prompt(session, ws, WebServerConfig(), "original", pending, Mock(), None))

    assert seen == ["original", "late steer", "queue one", "queue two", "queue three"]
    assert pending == []
    assert [event["content"] for event in sent] == seen[1:]
    assert [event["mode"] for event in sent] == ["steer", "queue", "queue", "queue"]


def test_socket_reader_and_turn_runner_apply_steering_before_queued_turns(monkeypatch):
    async def run():
        incoming = asyncio.Queue()
        first_token = asyncio.Event()
        inputs_received = asyncio.Event()
        finish_round = asyncio.Event()
        sent = []
        received = 0

        async def receive():
            nonlocal received
            frame = await incoming.get()
            received += 1
            if received == 3:
                inputs_received.set()
            return json.dumps(frame)

        async def send(event):
            sent.append(event)

        async def stream(prompt, messages, steering_prompts, **kwargs):
            messages.append({"role": "user", "content": prompt})
            yield TokenEvent(content="working")
            if prompt == "original":
                first_token.set()
                await finish_round.wait()
            messages.append({"role": "assistant", "content": "response"})
            for event in loop._apply_steering(messages, steering_prompts):
                yield event
            if messages[-1]["role"] == "user":
                messages.append({"role": "assistant", "content": "steered response"})
            yield DoneEvent(full_content=messages[-1]["content"], message_count=len(messages))

        monkeypatch.setattr(chat, "stream_prompt", stream)
        session = ConversationSession(session_id="s1", provider="openai", model="test", title="Existing")
        ws = SimpleNamespace(receive_text=receive, send_json=send)
        sessions = Mock()
        task = asyncio.create_task(chat._process_prompt(session, ws, WebServerConfig(), "original", [], sessions))
        await first_token.wait()
        for mode, content in [("queue", "queue one"), ("queue", "queue two"), ("steer", "adjust")]:
            await incoming.put({"type": "prompt", "mode": mode, "content": content})
        await inputs_received.wait()
        finish_round.set()
        await task

        assert [m["content"] for m in session.messages if m["role"] == "user"] == [
            "original", "adjust", "queue one", "queue two",
        ]
        starts = [(i, event) for i, event in enumerate(sent) if event["type"] == "prompt_started"]
        completions = [i for i, event in enumerate(sent) if event["type"] == "done"]
        assert [event["mode"] for _, event in starts] == ["steer", "queue", "queue"]
        assert starts[0][0] < completions[0] < starts[1][0] < completions[1] < starts[2][0] < completions[2]
        assert sessions.persist.call_count == 3

    asyncio.run(asyncio.wait_for(run(), timeout=3))


@pytest.mark.parametrize("mode", ["steer", "queue"])
def test_busy_submission_arriving_after_done_starts_a_new_turn(monkeypatch, mode):
    process = AsyncMock()
    monkeypatch.setattr(chat, "_process_prompt", process)
    ws = SimpleNamespace(send_json=AsyncMock())
    session = ConversationSession(session_id="s1")
    asyncio.run(
        chat._dispatch_client_message(
            ws, session, "s1", Mock(), WebServerConfig(), Mock(),
            {"type": "prompt", "content": "late", "mode": mode},
        )
    )
    assert process.await_count == 1
    assert ws.send_json.await_args.args[0] == {"type": "prompt_started", "content": "late", "mode": mode}


def test_cancel_clears_both_inboxes_and_rolls_back_only_the_current_turn():
    async def run():
        session = ConversationSession(session_id="s1", messages=[{"role": "system", "content": "keep"}])
        pending, steering = ["later"], ["adjust"]
        ws = SimpleNamespace(
            receive_text=AsyncMock(return_value=json.dumps({"type": "cancel"})),
            send_json=AsyncMock(),
        )

        async def stream(prompt, messages, **kwargs):
            messages.append({"role": "user", "content": prompt})
            yield TokenEvent(content="partial")
            await asyncio.Event().wait()

        await asyncio.wait_for(
            chat_helpers._run_turn(
                session, ws, "original", WebServerConfig(), pending,
                stream_fn=stream, steering_prompts=steering,
            ),
            timeout=2,
        )
        assert session.messages == [{"role": "system", "content": "keep"}]
        assert session.history_turns == []
        assert pending == steering == []
        assert ws.send_json.await_args.args[0]["type"] == "cancelled"

    asyncio.run(run())


def test_agent_error_rolls_back_and_does_not_execute_pending_messages():
    async def run():
        session = ConversationSession(session_id="s1")
        pending, steering = ["later"], ["adjust"]

        async def receive():
            await asyncio.Event().wait()

        ws = SimpleNamespace(receive_text=receive, send_json=AsyncMock())
        sessions = Mock()

        async def stream(prompt, messages, **kwargs):
            messages.append({"role": "user", "content": prompt})
            yield ErrorEvent(message="failed")

        await asyncio.wait_for(
            chat_helpers._run_prompt_turn(
                session, ws, "original", WebServerConfig(), pending, sessions,
                stream_fn=stream, steering_prompts=steering,
            ),
            timeout=2,
        )
        assert session.messages == []
        assert pending == steering == []
        assert ws.send_json.await_count == 1
        assert ws.send_json.await_args.args[0]["type"] == "error"
        sessions.persist.assert_called_once_with(session)

    asyncio.run(run())
