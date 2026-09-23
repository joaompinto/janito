"""Web agent stream_prompt end-to-end tests.

Split from ``test_web_api_types.py`` (fake-client round trips against the
Responses runner).
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod

try:
    import dashscope  # noqa: F401

    _HAS_DASHSCOPE = True
except ModuleNotFoundError:
    _HAS_DASHSCOPE = False

requires_dashscope = pytest.mark.skipif(not _HAS_DASHSCOPE, reason="dashscope package is not installed")

FRONTEND = Path(__file__).parent.parent.parent / "janito" / "web" / "frontend"


@pytest.fixture(scope="module", autouse=True)
def clean_config(request):
    """Isolate the config dir in a temp dir so tests never touch the real one."""
    prev_dir = config_dir_mod.get_config_dir()
    tmp = tempfile.mkdtemp(prefix="janito_web_api_types_tests_")
    config_dir_mod.set_config_dir(tmp)

    def restore():
        config_dir_mod.set_config_dir(str(prev_dir))

    request.addfinalizer(restore)


# ---------------------------------------------------------------------------
# End-to-end: stream_prompt against a fake Responses client
# ---------------------------------------------------------------------------


class _FakeStream:
    """An async iterable of fake SDK events/chunks."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return self._items.pop(0)
        except IndexError:
            raise StopAsyncIteration


class _FakeResponsesApi:
    def __init__(self, owner):
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        return _FakeStream(self._owner.streams.pop(0))


class _FakeClient:
    """Fake SDK client recording each call and replaying the given streams."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.responses = _FakeResponsesApi(self)


def test_stream_prompt_responses_round_trip(monkeypatch):
    """The loop dispatches to the Responses runner, keeps the history in
    OpenAI format, and re-sends the converted history after a tool round."""
    import asyncio

    from janito.web.backend.agent import loop
    from janito.web.backend.config import WebServerConfig
    from janito.web.backend.events import DoneEvent, TokenEvent, WaitingEvent

    monkeypatch.setattr(
        loop,
        "resolve_runtime_config",
        lambda *a, **k: (None, "sk-test", "gpt-4"),
    )

    fake_client = _FakeClient(
        [
            # First round: a tool call (no final text yet).
            [
                SimpleNamespace(type="response.output_text.delta", delta="Let me check."),
                SimpleNamespace(
                    type="response.function_call_arguments.done",
                    item_id="fc1",
                    arguments='{"filepath": "/tmp/a"}',
                ),
                SimpleNamespace(
                    type="response.output_item.done",
                    item=SimpleNamespace(
                        type="function_call",
                        call_id="call_1",
                        name="ReadFile",
                        id="fc1",
                    ),
                ),
                SimpleNamespace(type="response.completed", response=SimpleNamespace(id="r1")),
            ],
            # Second round: the final answer.
            [
                SimpleNamespace(type="response.output_text.delta", delta="Done!"),
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(
                        id="r2",
                        usage=SimpleNamespace(total_tokens=8, input_tokens=5, output_tokens=3),
                    ),
                ),
            ],
        ]
    )
    monkeypatch.setattr(
        "janito.web.backend.agent.responses.create_client",
        lambda base_url, api_key: fake_client,
    )

    async def _fake_run_tool_turn(
        tool_calls_list,
        full_content,
        messages,
        use_mcp,
        thought_parts=None,
        allowed_tools=None,
    ):
        # Mirror run_tool_turn's OpenAI-format appends without executing tools.
        assert allowed_tools is not None  # the loop always passes the gate
        assistant_msg = {
            "role": "assistant",
            "content": full_content or None,
            "tool_calls": tool_calls_list,
        }
        if thought_parts:
            assistant_msg["thought_parts"] = thought_parts
        messages.append(assistant_msg)
        for tc in tool_calls_list:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": "{}",
                }
            )
        return
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(loop, "run_tool_turn", _fake_run_tool_turn)

    config = WebServerConfig(provider="openai", no_tools=True, verbose=False)
    messages: list[dict] = []

    async def _run():
        events = []
        async for ev in loop.stream_prompt("hi", messages, config, tools=[], use_mcp=False):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    client = fake_client

    # The history stays in the portable OpenAI chat format.
    assert messages == [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "Let me check.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "ReadFile",
                        "arguments": '{"filepath": "/tmp/a"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "ReadFile", "content": "{}"},
        {"role": "assistant", "content": "Done!"},
    ]

    # Two API rounds: the first carries the user prompt, the second re-sends
    # the whole history including the function_call + function_call_output
    # items produced by the tool round.
    assert len(client.calls) == 2
    first_input = client.calls[0]["input"]
    assert first_input == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hi"}],
        }
    ]
    second_input = client.calls[1]["input"]
    # The second round re-sends the whole (converted) history as it stood
    # when the request was made: user prompt, the assistant's tool-call turn
    # (text + function_call), and the tool result.
    assert second_input == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hi"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Let me check."}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "ReadFile",
            "arguments": '{"filepath": "/tmp/a"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "{}",
        },
    ]

    # Event flow: waiting -> token -> tool turn (no events) -> waiting ->
    # token -> usage -> done.
    assert isinstance(events[0], WaitingEvent)
    assert isinstance(events[1], TokenEvent) and events[1].content == "Let me check."
    assert isinstance(events[2], WaitingEvent)
    assert isinstance(events[3], TokenEvent) and events[3].content == "Done!"
    usage = next(e for e in events if getattr(e, "type", "") == "usage")
    assert (usage.last_input, usage.last_output, usage.total) == (5, 3, 8)
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.full_content == "Done!"
    assert done.message_count == len(messages)


def test_stream_prompt_responses_emits_image_event(monkeypatch):
    """A native image_generation_call becomes an ImageEvent and the image
    path is persisted on the assistant message for history reload."""
    import asyncio
    import base64
    import os

    from janito.web.backend.agent import loop
    from janito.web.backend.config import WebServerConfig
    from janito.web.backend.events import DoneEvent, ImageEvent, TokenEvent

    monkeypatch.setattr(
        loop,
        "resolve_runtime_config",
        lambda *a, **k: (None, "sk-test", "gpt-6-sol"),
    )

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDRjunk"
    fake_client = _FakeClient(
        [
            [
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta="Here is your image:",
                ),
                SimpleNamespace(
                    type="response.output_item.done",
                    item=SimpleNamespace(
                        type="image_generation_call",
                        id="img_1",
                        result=base64.b64encode(png_bytes).decode(),
                        revised_prompt="A tabby cat hugging an otter",
                    ),
                ),
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(
                        id="r1",
                        usage=SimpleNamespace(total_tokens=8, input_tokens=5, output_tokens=3),
                    ),
                ),
            ],
        ]
    )
    monkeypatch.setattr(
        "janito.web.backend.agent.responses.create_client",
        lambda base_url, api_key: fake_client,
    )

    config = WebServerConfig(provider="openai", no_tools=True, verbose=False)
    messages: list[dict] = []

    async def _run():
        events = []
        async for ev in loop.stream_prompt("draw a cat", messages, config, tools=[], use_mcp=False):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    # The image result is surfaced as an ImageEvent with a saved temp PNG,
    # and the turn still ends with a normal DoneEvent.
    image_events = [e for e in events if isinstance(e, ImageEvent)]
    assert len(image_events) == 1
    img_path = image_events[0].path
    assert os.path.isfile(img_path) and img_path.endswith(".png")
    with open(img_path, "rb") as fh:
        assert fh.read() == png_bytes

    tokens = [e for e in events if isinstance(e, TokenEvent)]
    assert [t.content for t in tokens] == ["Here is your image:"]
    assert isinstance(events[-1], DoneEvent)

    # The saved image path is persisted on the assistant message so the
    # frontend can rebuild the content card from history.
    assistant_msg = [m for m in messages if m["role"] == "assistant"][0]
    assert assistant_msg["content"] == "Here is your image:"
    assert assistant_msg["images"] == [{"path": img_path, "revised_prompt": "A tabby cat hugging an otter"}]

    # The image_generation tool was advertised to the model (gpt-6 model).
    assert fake_client.calls[0]["tools"][-1] == {"type": "image_generation"}

    os.remove(img_path)


# ---------------------------------------------------------------------------
# End-to-end: stream_prompt against a fake Chat Completions client
# ---------------------------------------------------------------------------


class _FakeCompletionsApi:
    def __init__(self, owner):
        self._owner = owner

    async def create(self, **kwargs):
        # Snapshot the conversation: the loop passes the caller-owned list by
        # reference and mutates it after the call returns.
        kwargs = dict(kwargs)
        kwargs["messages"] = list(kwargs["messages"])
        self._owner.calls.append(kwargs)
        return _FakeStream(self._owner.streams.pop(0))


class _FakeCompletionsClient:
    """Fake OpenAI SDK client recording each call and replaying chunks."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.chat = SimpleNamespace(completions=_FakeCompletionsApi(self))


def test_stream_prompt_completions_round_trip(monkeypatch):
    """Completions runs through its own runner module: the loop builds the
    turn via ``janito.web.backend.agent.completions`` (messages + tools on
    the shared adapter's kwargs) and streams reasoning/token events, ending
    with a usage event and a DoneEvent -- same behaviour as before the
    extraction from loop.py."""
    import asyncio

    from janito.web.backend.agent import loop
    from janito.web.backend.config import WebServerConfig
    from janito.web.backend.events import (
        DoneEvent,
        ReasoningEvent,
        TokenEvent,
        WaitingEvent,
    )

    monkeypatch.setattr(
        loop,
        "resolve_runtime_config",
        lambda *a, **k: (None, "sk-test", "gpt-4"),
    )

    def _chunk(content=None, reasoning=None, usage=None):
        return SimpleNamespace(
            id="chatcmpl-1",
            model="gpt-4",
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(
                        content=content,
                        reasoning_content=reasoning,
                        tool_calls=None,
                    ),
                    finish_reason=None,
                )
            ],
            usage=usage,
        )

    fake_client = _FakeCompletionsClient(
        [
            [
                _chunk(reasoning="Let me think..."),
                _chunk(content="Hi there!"),
                _chunk(
                    usage=SimpleNamespace(
                        total_tokens=10,
                        prompt_tokens=6,
                        completion_tokens=4,
                        prompt_tokens_details=SimpleNamespace(cached_tokens=2),
                    )
                ),
            ]
        ]
    )
    monkeypatch.setattr(
        "janito.web.backend.agent.completions.create_client",
        lambda base_url, api_key: fake_client,
    )

    config = WebServerConfig(provider="openai", api_type="Completions", no_tools=True, verbose=False)
    messages: list[dict] = []

    async def _run():
        events = []
        async for ev in loop.stream_prompt("hi", messages, config, tools=[], use_mcp=False):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    # The chat.completions kwargs carry the conversation; with no_tools there
    # are no function tools on the call.
    call = fake_client.calls[0]
    assert call["model"] == "gpt-4"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert "tools" not in call

    # Reasoning + content deltas stream as events; usage and done follow.
    assert isinstance(events[0], WaitingEvent)
    assert isinstance(events[1], ReasoningEvent) and events[1].content == "Let me think..."
    assert isinstance(events[2], TokenEvent) and events[2].content == "Hi there!"
    usage = next(e for e in events if getattr(e, "type", "") == "usage")
    assert (usage.last_input, usage.last_cached, usage.last_output, usage.total) == (
        6,
        2,
        4,
        10,
    )
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.full_content == "Hi there!"
    assert done.message_count == len(messages)

    # The assistant message keeps reasoning_content for follow-up turns.
    assert messages[-1] == {
        "role": "assistant",
        "content": "Hi there!",
        "reasoning_content": "Let me think...",
    }
