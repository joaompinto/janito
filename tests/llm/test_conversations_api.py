"""
Tests for the Responses API client (:mod:`janito.llm_clients.openai.conversations_api`).

``conversations_api.run_turn`` mirrors ``completions_api.run_turn`` but
targets the Responses API (``client.responses.create``) with server-side
conversation state: the client never stores or updates a ``messages`` list,
and turns are chained with ``previous_response_id``.

These tests verify:
  - ``_consume_response_stream`` text / reasoning / tool-call assembly.
  - ``response.failed`` is turned into a raised error.
  - ``run_turn`` chains tool-call rounds via ``previous_response_id`` and
    returns a ``ConversationResult`` carrying the final server-side response
    id (no client-side history is kept or mutated).
  - ``instructions`` are only sent on the first turn of a conversation.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest import mock

import pytest
from conftest import make_config, make_ui_config

import janito.config_dir as config_dir_mod
import janito.tooling.used_files as used_files
from janito.llm_adapters.responses import _convert_tools_to_responses_format
from janito.llm_clients.openai import conversations_api as api
from janito.llm_clients.openai.responses_stream import _consume_response_stream
from janito.providers.models import ModelConfig


def _responses_config(model="gpt-4o", provider="openai"):
    """Minimal Responses APIConfig for the mocked-network tests."""
    return make_config(
        api_type="Responses",
        provider=provider,
        model=model,
        base_url="https://api.example.com",
        use_mcp=False,
    )


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Run each test in a temp CWD with a temp config dir and clean state.

    ``run_turn`` resets the in-process used-files tracker and clears the
    ``./.janito/changes.jsonl`` log (relative to the CWD), so each test gets
    its own temp dirs and the in-memory tracker is reset before and after.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path)
    used_files.reset_used_files()
    yield
    used_files.reset_used_files()


# ---- Minimal stand-ins for the SDK's typed stream events -----------------


class _Event:
    """Fake stream event; ``type`` plus arbitrary attributes."""

    def __init__(self, type, **attrs):
        self.type = type
        for name, value in attrs.items():
            setattr(self, name, value)


class _Response:
    def __init__(self, id, usage=None, error=None):
        self.id = id
        self.usage = usage
        self.error = error


class _FunctionCallItem:
    def __init__(self, id, call_id, name, arguments=None):
        self.id = id
        self.type = "function_call"
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


class _Usage:
    total_tokens = 100
    input_tokens = 60
    output_tokens = 40
    input_tokens_details = type("Details", (), {"cached_tokens": 5})()


def _stream(events):
    yield from events


# ---- _consume_response_stream -------------------------------------------


def test_consume_stream_assembles_text_and_usage():
    events = _stream(
        [
            _Event("response.created", response=_Response("resp_1")),
            _Event("response.output_text.delta", delta="Hello"),
            _Event("response.output_text.delta", delta=" world"),
            _Event("response.completed", response=_Response("resp_1", usage=_Usage())),
        ]
    )
    (
        content,
        reasoning,
        tools,
        usage,
        response_id,
        raw_attrs,
        _reasoning_items,
        _web_search_calls,
        _web_search_citations,
    ) = _consume_response_stream(events)
    assert content == "Hello world"
    assert reasoning is None
    assert tools == []
    assert response_id == "resp_1"
    assert usage.total_tokens == 100
    assert usage.input_tokens_details.cached_tokens == 5


def test_consume_stream_assembles_split_tool_call_arguments():
    events = _stream(
        [
            _Event("response.created", response=_Response("resp_2")),
            _Event("response.reasoning_text.delta", delta="thinking..."),
            _Event(
                "response.function_call_arguments.delta",
                item_id="fc_1",
                delta='{"path":',
            ),
            _Event(
                "response.function_call_arguments.delta",
                item_id="fc_1",
                delta=' "/tmp/a"}',
            ),
            _Event(
                "response.output_item.done",
                item=_FunctionCallItem("fc_1", "call_1", "read_file"),
            ),
            _Event("response.output_text.delta", delta="Let me check"),
            _Event("response.completed", response=_Response("resp_2")),
        ]
    )
    (
        content,
        reasoning,
        tools,
        usage,
        response_id,
        raw_attrs,
        _reasoning_items,
        _web_search_calls,
        _web_search_citations,
    ) = _consume_response_stream(events)
    assert content == "Let me check"
    assert reasoning == "thinking..."
    assert tools == [{"call_id": "call_1", "name": "read_file", "arguments": '{"path": "/tmp/a"}'}]
    assert response_id == "resp_2"


def test_consume_stream_prefers_full_arguments_from_done_event():
    events = _stream(
        [
            _Event("response.created", response=_Response("resp_3")),
            _Event(
                "response.function_call_arguments.done",
                item_id="fc_1",
                arguments='{"x": 1}',
            ),
            _Event(
                "response.output_item.done",
                item=_FunctionCallItem("fc_1", "call_9", "run_bash", '{"x": 1}'),
            ),
            _Event("response.completed", response=_Response("resp_3")),
        ]
    )
    _, _, tools, _, response_id, _, _, _, _ = _consume_response_stream(events)
    assert tools == [{"call_id": "call_9", "name": "run_bash", "arguments": '{"x": 1}'}]
    assert response_id == "resp_3"


def test_consume_stream_raises_on_failed_response():
    events = _stream(
        [
            _Event("response.created", response=_Response("resp_4")),
            _Event(
                "response.failed",
                response=_Response("resp_4", error=type("E", (), {"message": "boom"})()),
            ),
        ]
    )
    with pytest.raises(RuntimeError, match="boom"):
        _consume_response_stream(events)


def test_consume_stream_raises_on_untyped_error_event():
    """Some providers (e.g. Alibaba DashScope's /responses endpoint) stream
    API errors as SSE events the SDK cannot type: ``event.type`` is None but
    the payload carries the error as ``code``/``message`` attributes (e.g.
    ``code='InvalidParameter'``, ``message="Unsupported model:
    'qwen3.8-max'."``). These must raise instead of silently returning an
    empty response."""
    events = _stream(
        [
            _Event(
                None,
                code="InvalidParameter",
                message="Unsupported model: 'qwen3.8-max'.",
                request_id="req_1",
            )
        ]
    )
    with pytest.raises(RuntimeError, match="Unsupported model: 'qwen3.8-max'"):
        _consume_response_stream(events)


def test_consume_stream_raises_on_empty_stream():
    """A stream that yields no events at all must raise rather than silently
    returning an empty response."""
    with pytest.raises(RuntimeError, match="empty response"):
        _consume_response_stream(_stream([]))


# ---- _convert_tools_to_responses_format ----------------------------------


def test_convert_tools_to_responses_format_lifts_name_to_top_level():
    """Chat Completions schemas (name nested under 'function') are converted
    to the Responses API shape (name/description/parameters at the top level)."""
    completions_schemas = [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "svc_mcp_tool",
                "description": "[svc] MCP tool",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                },
            },
        },
    ]
    converted = _convert_tools_to_responses_format(completions_schemas)
    assert converted == [
        {
            "type": "function",
            "name": "list_files",
            "description": "List files",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "svc_mcp_tool",
            "description": "[svc] MCP tool",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        },
    ]
    # Every converted tool carries the top-level 'name' the Responses API
    # requires (missing it caused "tools[0]: missing field 'name'").
    assert all("name" in tool for tool in converted)


def test_convert_tools_to_responses_format_handles_already_converted_and_empty():
    # A schema that already has top-level name (no nested 'function') is kept.
    already = {"type": "function", "name": "x", "parameters": {}}
    assert _convert_tools_to_responses_format([already]) == [
        {"type": "function", "name": "x", "description": "", "parameters": {}}
    ]
    # An empty list stays empty.
    assert _convert_tools_to_responses_format([]) == []


# ---- run_turn (mocked network) ----------------------------------------


def _mock_run_turn(monkeypatch, create_side_effect):
    """Patch config resolution, tool schemas, the executor and the client."""
    client_inst = mock.Mock()
    client_inst.responses.create.side_effect = create_side_effect
    monkeypatch.setattr(api, "OpenAI", mock.Mock(return_value=client_inst))
    monkeypatch.setattr(
        "janito.llm_clients.openai.responses_helpers.get_session_tool_schemas",
        lambda: [{"type": "function", "function": {"name": "list_files"}}],
    )
    executor_inst = mock.Mock()
    executor_inst.execute_tool_call.return_value = {
        "tool_call_id": "call_1",
        "role": "tool",
        "name": "list_files",
        "content": json.dumps({"success": True}),
    }
    monkeypatch.setattr(api, "ToolExecutor", mock.Mock(return_value=executor_inst))
    return client_inst


def _mock_run_turn_for_model(monkeypatch, model, builtin_tools, create_side_effect):
    """Like ``_mock_run_turn`` but for a specific model, with the model's
    built-in (native) tools resolved via the typed provider accessor."""
    client_inst = mock.Mock()
    client_inst.responses.create.side_effect = create_side_effect
    monkeypatch.setattr(api, "OpenAI", mock.Mock(return_value=client_inst))
    monkeypatch.setattr(
        "janito.llm_clients.openai.responses_helpers.get_session_tool_schemas",
        lambda: [{"type": "function", "function": {"name": "list_files"}}],
    )
    monkeypatch.setattr(
        "janito.llm_clients.openai.conversations_api.get_provider",
        lambda p: mock.Mock(tools=lambda model=None, api_type=None: builtin_tools),
    )
    executor_inst = mock.Mock()
    executor_inst.execute_tool_call.return_value = {
        "tool_call_id": "call_1",
        "role": "tool",
        "name": "list_files",
        "content": json.dumps({"success": True}),
    }
    monkeypatch.setattr(api, "ToolExecutor", mock.Mock(return_value=executor_inst))
    return client_inst


def test_run_turn_stateless_replays_full_history(monkeypatch):
    """Stateless providers (stateless_mode False, e.g. DeepSeek) cannot
    resolve a previous_response_id: the client re-sends the full conversation
    as input items on every request and never chains with an id."""
    monkeypatch.setattr(
        "janito.llm_clients.openai.responses_state.get_provider",
        lambda p: mock.Mock(model_config=lambda model=None: ModelConfig({"stateless_mode": True})),
    )
    seen = []

    def create(**kwargs):
        # Snapshot the input list: run_turn appends to the same list in
        # place after the request, so re-checking kwargs later would see the
        # mutated history.
        seen.append(dict(kwargs, input=list(kwargs["input"])))
        round_no = len(seen)
        if round_no == 1:
            # First round: input is a fresh items list (system instructions
            # folded in, then the user prompt); no previous_response_id and no
            # instructions kwarg (already part of the items).
            assert "previous_response_id" not in kwargs
            assert "instructions" not in kwargs
            assert kwargs["input"] == [
                {
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "input_text", "text": "Be helpful"}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "List files"}],
                },
            ]
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_a")),
                    _Event(
                        "response.output_item.done",
                        item=_FunctionCallItem("it1", "call_1", "list_files", "{}"),
                    ),
                    _Event("response.completed", response=_Response("resp_a")),
                ]
            )
        if round_no == 2:
            # Tool round: the full history (system + user + function_call +
            # function_call_output) is re-sent; never chained with an id.
            assert "previous_response_id" not in kwargs
            assert kwargs["input"] == [
                {
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "input_text", "text": "Be helpful"}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "List files"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "list_files",
                    "arguments": "{}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": json.dumps({"success": True}),
                },
            ]
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_b")),
                    _Event("response.output_text.delta", delta="Here are the files"),
                    _Event(
                        "response.completed",
                        response=_Response("resp_b", usage=_Usage()),
                    ),
                ]
            )
        raise AssertionError(f"unexpected round {round_no}")

    _mock_run_turn(monkeypatch, create)

    result = api.run_turn(_responses_config(), "List files", instructions="Be helpful", tools=None)

    assert result.content == "Here are the files"
    # Stateless: no server-side handle to chain with.
    assert result.response_id is None
    assert result.message_count == 2
    assert len(seen) == 2
    # The result carries the full client-side history for the next turn.
    assert result.input_items is not None
    assert result.input_items[-1] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Here are the files"}],
    }


def test_run_turn_stateless_continues_with_previous_items(monkeypatch):
    """The next turn re-sends the previous turn's items plus the new prompt."""
    monkeypatch.setattr(
        "janito.llm_clients.openai.responses_state.get_provider",
        lambda p: mock.Mock(model_config=lambda model=None: ModelConfig({"stateless_mode": True})),
    )
    seen = []

    def create(**kwargs):
        # Snapshot the input list (run_turn mutates it in place later).
        seen.append(dict(kwargs, input=list(kwargs["input"])))
        assert "previous_response_id" not in kwargs
        return _stream(
            [
                _Event("response.created", response=_Response("resp_n")),
                _Event("response.output_text.delta", delta="ok"),
                _Event("response.completed", response=_Response("resp_n")),
            ]
        )

    _mock_run_turn(monkeypatch, create)

    # First turn (fresh conversation).
    first = api.run_turn(_responses_config(), "Hello", instructions="Sys", tools=[])
    assert seen[-1]["input"] == [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": "Sys"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}],
        },
    ]

    # Second turn: the full history is re-sent with the new user prompt
    # appended; instructions are NOT folded again (already in the history).
    second = api.run_turn(
        _responses_config(),
        "Follow up",
        previous_items=first.input_items,
        instructions="Sys",
        tools=[],
    )
    assert seen[-1]["input"] == first.input_items + [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Follow up"}],
        }
    ]
    assert second.input_items == seen[-1]["input"] + [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "ok"}],
        }
    ]


class _ReasoningItem:
    """Fake finished ``reasoning`` output item (encrypted chain of thought)."""

    def __init__(self, id, encrypted_content, summary=None):
        self.id = id
        self.type = "reasoning"
        self.encrypted_content = encrypted_content
        self.summary = summary if summary is not None else []


def test_run_turn_stateless_sends_store_false_and_include(monkeypatch):
    """Stateless providers send ``store: False`` plus the model's declared
    ``responses_include`` values (e.g. Meta's reasoning.encrypted_content)
    on every request, and never chain with a response id."""
    monkeypatch.setattr(
        "janito.llm_clients.openai.responses_state.get_provider",
        lambda p: mock.Mock(
            model_config=lambda model=None: ModelConfig(
                {
                    "stateless_mode": True,
                    "responses_include": ["reasoning.encrypted_content"],
                }
            ),
        ),
    )
    seen = []

    def create(**kwargs):
        seen.append(dict(kwargs, input=list(kwargs["input"])))
        assert kwargs["store"] is False
        assert kwargs["include"] == ["reasoning.encrypted_content"]
        assert "previous_response_id" not in kwargs
        return _stream(
            [
                _Event("response.created", response=_Response("resp_n")),
                _Event("response.output_text.delta", delta="ok"),
                _Event("response.completed", response=_Response("resp_n")),
            ]
        )

    _mock_run_turn(monkeypatch, create)
    result = api.run_turn(_responses_config(), "Hello", tools=[])
    assert result.response_id is None


def test_run_turn_stateless_replays_reasoning_items(monkeypatch):
    """Stateless providers replay the finished ``reasoning`` output items
    (the encrypted chain of thought) in the next round's ``input``, in the
    order the stream emitted them (reasoning item -> assistant message /
    function_call) and keep them in the items carried across turns."""
    monkeypatch.setattr(
        "janito.llm_clients.openai.responses_state.get_provider",
        lambda p: mock.Mock(
            model_config=lambda model=None: ModelConfig(
                {
                    "stateless_mode": True,
                    "responses_include": ["reasoning.encrypted_content"],
                }
            ),
        ),
    )
    seen = []
    reasoning_item = {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [],
        "encrypted_content": "ENCRYPTED",
    }

    def create(**kwargs):
        seen.append(dict(kwargs, input=list(kwargs["input"])))
        round_no = len(seen)
        if round_no == 1:
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_a")),
                    _Event(
                        "response.output_item.done",
                        item=_ReasoningItem("rs_1", "ENCRYPTED"),
                    ),
                    _Event("response.output_text.delta", delta="Working"),
                    _Event(
                        "response.output_item.done",
                        item=_FunctionCallItem("it1", "call_1", "list_files", "{}"),
                    ),
                    _Event(
                        "response.completed",
                        response=_Response("resp_a", usage=_Usage()),
                    ),
                ]
            )
        # Round 2 (tool round): the reasoning item is replayed verbatim,
        # followed by the assistant text and the function_call items.
        assert kwargs["input"] == [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "List files"}],
            },
            reasoning_item,
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Working"}],
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "list_files",
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": json.dumps({"success": True}),
            },
        ]
        return _stream(
            [
                _Event("response.created", response=_Response("resp_b")),
                _Event("response.output_text.delta", delta="Here are the files"),
                _Event(
                    "response.completed",
                    response=_Response("resp_b", usage=_Usage()),
                ),
            ]
        )

    _mock_run_turn(monkeypatch, create)

    result = api.run_turn(_responses_config(), "List files", tools=None)
    assert result.content == "Here are the files"
    # The final items history carries the reasoning item too, positioned
    # between the user prompt and the assistant turn it belongs to.
    assert result.input_items[1] == reasoning_item


def test_run_turn_server_side_never_sends_store_or_include(monkeypatch):
    """Server-side providers (e.g. OpenAI) send neither ``store`` nor
    ``include``: the defaults apply (store:true is what makes the
    previous_response_id chaining work)."""
    seen = []

    def create(**kwargs):
        seen.append(dict(kwargs, input=kwargs["input"]))
        assert "store" not in kwargs
        assert "include" not in kwargs
        return _stream(
            [
                _Event("response.created", response=_Response("resp_n")),
                _Event("response.output_text.delta", delta="ok"),
                _Event("response.completed", response=_Response("resp_n")),
            ]
        )

    _mock_run_turn(monkeypatch, create)
    result = api.run_turn(_responses_config(), "Hello", tools=None)
    assert result.response_id == "resp_n"


def test_run_turn_plain_response(monkeypatch):
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        assert kwargs["input"] == "Hello"
        # "usage" is no longer a valid include value: usage arrives on the
        # final response.completed event by default (part of the Response
        # object), so no include parameter is sent.
        assert "include" not in kwargs
        assert "previous_response_id" not in kwargs
        return _stream(
            [
                _Event("response.created", response=_Response("resp_1")),
                _Event("response.output_text.delta", delta="Hi there"),
                _Event("response.completed", response=_Response("resp_1", usage=_Usage())),
            ]
        )

    _mock_run_turn(monkeypatch, create)
    result = api.run_turn(_responses_config(), "Hello", tools=None)

    assert result.content == "Hi there"
    assert result.response_id == "resp_1"
    assert result.message_count == 1
    # Server-side conversation: no client-side items history to carry.
    assert result.input_items is None
    assert len(seen) == 1


def test_run_turn_raises_on_untyped_error_event(monkeypatch):
    """A server-side provider that streams an untyped error event (e.g.
    DashScope rejecting qwen3.8-max on /responses) must raise a clear error
    instead of returning an empty ConversationResult."""

    def create(**kwargs):
        return _stream(
            [
                _Event(
                    None,
                    code="InvalidParameter",
                    message="Unsupported model: 'qwen3.8-max'.",
                )
            ]
        )

    _mock_run_turn(monkeypatch, create)
    with pytest.raises(RuntimeError, match="Unsupported model: 'qwen3.8-max'"):
        api.run_turn(_responses_config(), "Hello", tools=None)


def test_run_turn_raises_on_empty_stream(monkeypatch):
    """A stream with no events at all raises instead of returning an empty
    result."""

    def create(**kwargs):
        return _stream([])

    _mock_run_turn(monkeypatch, create)
    with pytest.raises(RuntimeError, match="empty response"):
        api.run_turn(_responses_config(), "Hello", tools=None)


def test_run_turn_raises_when_no_response_id_and_no_output(monkeypatch):
    """A server-side provider that reports no response id and produces neither
    content nor tool calls raises an error naming the model (safety net for
    providers whose failure never surfaces as a proper event)."""

    def create(**kwargs):
        return _stream(
            [
                _Event("response.in_progress", response=_Response("unused")),
            ]
        )

    _mock_run_turn(monkeypatch, create)
    with pytest.raises(RuntimeError, match="gpt-4o"):
        api.run_turn(_responses_config(), "Hello", tools=None)


def test_run_turn_sends_instructions_on_every_server_side_turn(monkeypatch):
    """Server-side providers always re-send ``instructions``: some (e.g.
    Meta) do not persist them across ``previous_response_id`` turns and
    require the parameter on every request; re-sending is also correct for
    providers that fold them into the stored conversation (OpenAI)."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return _stream(
            [
                _Event("response.created", response=_Response("resp_n")),
                _Event("response.output_text.delta", delta="ok"),
                _Event("response.completed", response=_Response("resp_n")),
            ]
        )

    _mock_run_turn(monkeypatch, create)

    # Fresh conversation: instructions are sent.
    api.run_turn(_responses_config(), "First", instructions="Be helpful", tools=[])
    assert seen[-1]["instructions"] == "Be helpful"

    # Continuing a conversation: instructions are re-sent (the turn is
    # chained via previous_response_id, which does not carry them).
    api.run_turn(
        _responses_config(),
        "Follow up",
        previous_response_id="resp_prev",
        instructions="Be helpful",
        tools=[],
    )
    assert seen[-1]["instructions"] == "Be helpful"
    assert seen[-1]["previous_response_id"] == "resp_prev"

    # Tool-call rounds re-send them too (same chaining rule applies).
    api.run_turn(
        _responses_config(),
        "Third",
        previous_response_id="resp_prev",
        previous_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "pending"}],
            }
        ],
        instructions="Be helpful",
        tools=[],
    )
    assert seen[-1]["instructions"] == "Be helpful"


def test_run_turn_server_side_resends_pending_items_with_completed_id(
    monkeypatch,
):
    """Server-side Responses: after an Enter-cancel the next turn re-sends the
    cancelled message as input items chained from the last *completed*
    response id (the aborted response id is discarded by the provider and
    never used, so no previous_response_not_found)."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        assert kwargs["previous_response_id"] == "resp_prev"
        assert kwargs["input"] == [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "cancelled prompt"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "follow up"}],
            },
        ]
        return _stream(
            [
                _Event("response.created", response=_Response("resp_n")),
                _Event("response.output_text.delta", delta="ok"),
                _Event("response.completed", response=_Response("resp_n")),
            ]
        )

    _mock_run_turn(monkeypatch, create)

    result = api.run_turn(
        _responses_config(),
        "follow up",
        previous_response_id="resp_prev",
        previous_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "cancelled prompt"}],
            }
        ],
        instructions="Be helpful",
        tools=[],
    )
    assert result.response_id == "resp_n"
    # Server-side success: the pending items are folded into the server
    # conversation; no client-side items are carried forward.
    assert result.input_items is None


def test_run_turn_chains_tool_calls_without_client_history(monkeypatch):
    """The agent loop must chain tool rounds via previous_response_id and keep
    no client-side messages list (the caller-owned list is not touched)."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        round_no = len(seen)
        if round_no == 1:
            # First round: the model requests a tool call.
            assert kwargs["input"] == "List files"
            assert "previous_response_id" not in kwargs
            # Tools are converted from the Chat Completions shape (name nested
            # under "function") to the Responses API shape (top-level name).
            assert kwargs["tools"] == [
                {
                    "type": "function",
                    "name": "list_files",
                    "description": "",
                    "parameters": {},
                }
            ]
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_a")),
                    _Event(
                        "response.output_item.done",
                        item=_FunctionCallItem("it1", "call_1", "list_files", "{}"),
                    ),
                    _Event("response.completed", response=_Response("resp_a")),
                ]
            )
        if round_no == 2:
            # Second round: tool outputs are chained to the previous response.
            assert kwargs["previous_response_id"] == "resp_a"
            assert kwargs["input"] == [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": json.dumps({"success": True}),
                }
            ]
            assert kwargs["tools"] == [
                {
                    "type": "function",
                    "name": "list_files",
                    "description": "",
                    "parameters": {},
                }
            ]
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_b")),
                    _Event("response.output_text.delta", delta="Here are the files"),
                    _Event(
                        "response.completed",
                        response=_Response("resp_b", usage=_Usage()),
                    ),
                ]
            )
        raise AssertionError(f"unexpected round {round_no}")

    _mock_run_turn(monkeypatch, create)

    caller_history = [{"role": "system", "content": "seed"}]
    result = api.run_turn(_responses_config(), "List files", tools=None)

    assert result.content == "Here are the files"
    assert result.response_id == "resp_b"
    assert result.message_count == 2
    # Server-side conversation: the history lives on the server, so the
    # result carries no client-side items.
    assert result.input_items is None
    assert len(seen) == 2
    # The caller-owned history must be untouched: no client-side messages list
    # is created, appended to or updated by the Responses implementation.
    assert caller_history == [{"role": "system", "content": "seed"}]


def test_run_turn_server_side_turn_items_mirror_tool_round(monkeypatch):
    """Server-side Responses: the completed turn's display-only mirror
    (``turn_items``) records the user prompt, the tool-call round
    (function_call + function_call_output) and the final assistant text, so
    the shell can render /history even though the real conversation lives on
    the server (no client-side ``input_items`` are carried)."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        round_no = len(seen)
        if round_no == 1:
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_a")),
                    _Event(
                        "response.output_item.done",
                        item=_FunctionCallItem("it1", "call_1", "list_files", "{}"),
                    ),
                    _Event("response.completed", response=_Response("resp_a")),
                ]
            )
        if round_no == 2:
            return _stream(
                [
                    _Event("response.created", response=_Response("resp_b")),
                    _Event("response.output_text.delta", delta="Here are the files"),
                    _Event(
                        "response.completed",
                        response=_Response("resp_b", usage=_Usage()),
                    ),
                ]
            )
        raise AssertionError(f"unexpected round {round_no}")

    _mock_run_turn(monkeypatch, create)
    result = api.run_turn(_responses_config(), "List files", tools=None)

    assert result.content == "Here are the files"
    assert result.response_id == "resp_b"
    assert result.message_count == 2
    # Server-side conversation: no client-side items history to carry.
    assert result.input_items is None
    # The display-only mirror holds the full turn for /history.
    assert result.turn_items == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "List files"}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "list_files",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": json.dumps({"success": True}),
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Here are the files"}],
        },
    ]


def test_run_turn_server_side_turn_items_plain_response(monkeypatch):
    """Server-side Responses: a plain (no-tool) turn's display-only mirror
    holds just the user prompt and the assistant text."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return _stream(
            [
                _Event("response.created", response=_Response("resp_1")),
                _Event("response.output_text.delta", delta="Hi there"),
                _Event("response.completed", response=_Response("resp_1", usage=_Usage())),
            ]
        )

    _mock_run_turn(monkeypatch, create)
    result = api.run_turn(_responses_config(), "Hello", tools=None)

    assert result.input_items is None
    assert result.turn_items == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hi there"}],
        },
    ]


def test_run_turn_appends_builtin_tools_without_function_tools(monkeypatch):
    """An empty function-tools list (the ``--no-tools`` case): the effective
    model's built-in (native) tools are still enabled on the CLI Responses
    path.  They are model capabilities, not function tools -- mirroring the
    web agent (and the Responses ``image_generation`` tool)."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return _stream(
            [
                _Event("response.created", response=_Response("resp_a")),
                _Event("response.output_text.delta", delta="done"),
                _Event("response.completed", response=_Response("resp_a")),
            ]
        )

    _mock_run_turn_for_model(
        monkeypatch,
        "qwen3.8-max",
        [
            {"type": "code_interpreter"},
            {"type": "web_search"},
            {"type": "web_extractor"},
        ],
        create,
    )
    api.run_turn(_responses_config(model="qwen3.8-max", provider="alibaba"), "Hello", tools=[])
    assert seen[-1]["tools"] == [
        {"type": "code_interpreter"},
        {"type": "web_search"},
        {"type": "web_extractor"},
    ]
    assert seen[-1]["tool_choice"] == "auto"


def test_run_turn_merges_builtin_tools_with_function_tools(monkeypatch):
    """Function-tool schemas (converted to the Responses shape) come first,
    followed by the model's built-in (native) tools."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return _stream(
            [
                _Event("response.created", response=_Response("resp_a")),
                _Event("response.output_text.delta", delta="done"),
                _Event("response.completed", response=_Response("resp_a")),
            ]
        )

    _mock_run_turn_for_model(
        monkeypatch,
        "qwen3.8-max",
        [
            {"type": "code_interpreter"},
            {"type": "web_search"},
            {"type": "web_extractor"},
        ],
        create,
    )
    api.run_turn(_responses_config(model="qwen3.8-max", provider="alibaba"), "Hello", tools=None)
    assert seen[-1]["tools"] == [
        {
            "type": "function",
            "name": "list_files",
            "description": "",
            "parameters": {},
        },
        {"type": "code_interpreter"},
        {"type": "web_search"},
        {"type": "web_extractor"},
    ]
    assert seen[-1]["tool_choice"] == "auto"


def test_run_turn_no_builtin_tools_for_openai_responses(monkeypatch):
    """Models without built-in tools get no native entries appended."""
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return _stream(
            [
                _Event("response.created", response=_Response("resp_a")),
                _Event("response.output_text.delta", delta="done"),
                _Event("response.completed", response=_Response("resp_a")),
            ]
        )

    _mock_run_turn_for_model(monkeypatch, "gpt-4o", None, create)
    api.run_turn(_responses_config(model="gpt-4o", provider="openai"), "Hello", tools=None)
    # Only the converted function tools; no code_interpreter / web_search.
    assert seen[-1]["tools"] == [
        {
            "type": "function",
            "name": "list_files",
            "description": "",
            "parameters": {},
        }
    ]
    assert seen[-1]["tool_choice"] == "auto"


def test_conversation_result_defaults():
    result = api.ConversationResult(content="text", response_id="resp_1")
    assert result.message_count == 1


def test_runtime_config_resolver_moved_out_of_client_modules():
    # Runtime-config resolution moved to the config layer
    # (janito.runtime_config); the client modules no longer re-export it.
    from janito.runtime_config import resolve_runtime_config

    assert callable(resolve_runtime_config)
    assert not hasattr(api, "resolve_runtime_config")
    assert not hasattr(api, "get_env_config")


# ---- API-type selection (chat.py wrapper + shell state) -------------------


def test_make_turn_func_responses_dispatch(monkeypatch):
    """The single closure dispatches by ``config.api_type`` to the Responses
    client and forwards the union kwargs via ``client.run_turn`` (each backend's
    ``_init_conversation_state`` picks what it needs)."""
    import janito.cli.chat as chat_mod
    import janito.llm_clients.openai.conversations_api as conv_api

    captured = {}

    class FakeClient:
        def __init__(self, config, ui_config=None):
            captured["config"] = config

        def run_turn(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return api.ConversationResult(content="hi", response_id="resp_z")

    monkeypatch.setattr(conv_api, "ResponsesClient", FakeClient)

    func = chat_mod._make_turn_func(make_config(api_type="Responses", model="gpt-4", provider="openai"))
    result = func(
        "hello",
        previous_messages=[{"role": "system", "content": "x"}],
        previous_response_id="resp_y",
        previous_items=[{"type": "message", "role": "user", "content": []}],
        instructions="sys",
        tools=[],
    )

    assert isinstance(result, api.ConversationResult)
    assert result.response_id == "resp_z"
    assert captured["config"].api_type == "Responses"
    assert captured["previous_response_id"] == "resp_y"
    assert captured["previous_items"] == [{"type": "message", "role": "user", "content": []}]
    assert captured["instructions"] == "sys"
    assert captured["tools"] == []
    # previous_messages IS forwarded by the union signature (the Responses
    # backend ignores it -- each _init_conversation_state picks its own).
    assert captured["previous_messages"] == [{"role": "system", "content": "x"}]
    # No out-param is threaded: the client owns the TurnInfo and delivers
    # the end-of-turn report itself (issue #82).
    assert "usage_out" not in captured


def test_make_turn_func_completions_dispatch(monkeypatch):
    """In Completions mode the same closure forwards previous_messages (the
    history list is mutated in place by the Completions client) and returns
    the assistant text."""
    import janito.cli.chat as chat_mod
    import janito.llm_clients.openai.completions_api as comp_api

    captured = {}

    class FakeClient:
        def __init__(self, config, ui_config=None):
            captured["config"] = config

        def run_turn(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return "completions answer"

    monkeypatch.setattr(comp_api, "CompletionsClient", FakeClient)

    func = chat_mod._make_turn_func(make_config(api_type="Completions", model="gpt-4", provider="openai"))
    result = func(
        "hello",
        previous_messages=[{"role": "user", "content": "hello"}],
        previous_response_id="resp_y",
        instructions="sys",
        tools=None,
    )

    assert result == "completions answer"
    assert captured["config"].api_type == "Completions"
    assert captured["previous_messages"] == [{"role": "user", "content": "hello"}]
    # No out-param is threaded: the client owns the TurnInfo and delivers
    # the end-of-turn report itself (issue #82).
    assert "usage_out" not in captured


# ---- turn_factory (real-time /provider switch) -----------------------------


def test_turn_factory_honors_cli_model_for_startup_provider(monkeypatch):
    """The factory keeps ``--model`` for the provider it was given for and
    builds the config via build_api_config (the single resolution point),
    injecting the CLI's TUI runner and Rich observer at build time."""
    import janito.cli.chat as chat_mod

    captured = {}
    fake_config = make_config()

    def fake_build(**kwargs):
        captured.update(kwargs)
        return fake_config

    def fake_make(config, ui_config=None, session_verbose=False):
        captured["config"] = config
        captured["ui_config"] = ui_config
        captured["session_verbose"] = session_verbose
        return lambda prompt, **kw: "ok"

    monkeypatch.setattr(chat_mod, "build_api_config", fake_build)
    monkeypatch.setattr(chat_mod, "_make_turn_func", fake_make)

    factory = chat_mod._make_turn_factory(
        cli_api_type=None,
        cli_model="gpt-6-luna",
        cli_provider="openai",
        cli_effort=None,
    )
    send = factory("openai")
    send("hello", previous_messages=[])
    assert captured["cli_model"] == "gpt-6-luna"
    assert captured["cli_provider"] == "openai"
    assert captured["api_type"] == "Responses"  # openai's built-in default
    assert captured["config"] is fake_config
    # The CLI's TUI stream runner and Rich observer are injected via the
    # UIConfig, alongside the captured session verbose flag.
    assert captured["ui_config"].stream_runner is chat_mod._run_with_progress_bar
    assert isinstance(captured["ui_config"].observer, chat_mod.RichTurnObserver)
    assert captured["session_verbose"] is False


def test_turn_factory_resolves_new_provider_model_and_api_type(monkeypatch):
    """After a /provider switch the new provider's own model and API type are
    resolved (the startup ``--model`` does not leak into it)."""
    import janito.cli.chat as chat_mod

    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return make_config(api_type=kwargs["api_type"])

    def fake_make(config, **kwargs):
        return lambda prompt, **kw: "ok"

    monkeypatch.setattr(chat_mod, "build_api_config", fake_build)
    monkeypatch.setattr(chat_mod, "_make_turn_func", fake_make)

    factory = chat_mod._make_turn_factory(
        cli_api_type=None,
        cli_model="gpt-6-luna",  # startup --model, belongs to openai
        cli_provider="openai",
        cli_effort=None,
    )
    send = factory("moonshot")  # switched provider
    send("hello", previous_messages=[])
    # The new provider's built-in default model is used, not the startup one.
    assert captured["cli_model"] == "kimi-k3"
    assert captured["cli_provider"] == "moonshot"
    assert captured["api_type"] == "Completions"


def test_turn_factory_resolves_configured_model_for_new_provider(monkeypatch, tmp_path):
    """A configured model for the switched-to provider is picked up."""
    import janito.cli.chat as chat_mod
    import janito.config_dir as config_dir_mod

    config_path = tmp_path / ".janito" / "config.json"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
    from janito.config_store import set_config_value

    set_config_value("deepseek.model", "deepseek-v4-pro")

    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return make_config(api_type=kwargs["api_type"])

    def fake_make(config, **kwargs):
        return lambda prompt, **kw: "ok"

    monkeypatch.setattr(chat_mod, "build_api_config", fake_build)
    monkeypatch.setattr(chat_mod, "_make_turn_func", fake_make)

    factory = chat_mod._make_turn_factory(
        cli_api_type=None,
        cli_model=None,
        cli_provider="openai",
        cli_effort=None,
    )
    send = factory("deepseek")
    send("hello", previous_messages=[])
    assert captured["cli_model"] == "deepseek-v4-pro"
    assert captured["cli_provider"] == "deepseek"


def test_turn_factory_resolves_api_type_per_new_provider(monkeypatch):
    """The API type is re-resolved for the switched-to provider: moonshot's
    only supported type is Completions, openai's default is Responses."""
    import janito.cli.chat as chat_mod

    captured = {}

    def fake_build(**kwargs):
        captured["api_type"] = kwargs["api_type"]
        captured["cli_model"] = kwargs["cli_model"]
        captured["cli_provider"] = kwargs["cli_provider"]
        return make_config(api_type=kwargs["api_type"])

    def fake_make(config, **kwargs):
        return lambda prompt, **kw: "ok"

    monkeypatch.setattr(chat_mod, "build_api_config", fake_build)
    monkeypatch.setattr(chat_mod, "_make_turn_func", fake_make)

    factory = chat_mod._make_turn_factory(
        cli_api_type=None,
        cli_model=None,
        cli_provider="openai",
        cli_effort=None,
    )
    factory("moonshot")
    assert captured["api_type"] == "Completions"
    assert captured["cli_model"] == "kimi-k3"
    assert captured["cli_provider"] == "moonshot"

    factory("openai")
    assert captured["api_type"] == "Responses"
    # openai's default model is resolved inside build_api_config (cli_model
    # stays None, matching the old "resolved in-client" contract).
    assert captured["cli_model"] is None


def test_shell_tracks_and_resets_previous_response_id():
    """The interactive shell keeps the server-side response id and resets it
    on a fresh conversation (initialize_history), so a clear never chains to
    the old server conversation."""
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    assert shell.previous_response_id is None
    assert shell.conversation_items is None

    # Simulate a completed Responses turn: the run loop stores the id.
    shell.previous_response_id = "resp_1"
    assert shell.previous_response_id == "resp_1"

    # F2 / "clear" call initialize_history -> fresh server conversation.
    shell.initialize_history(system_prompt="You are helpful")
    assert shell.previous_response_id is None
    assert shell.conversation_items is None


def test_shell_tracks_stateless_conversation_items():
    """For stateless Responses providers (stateless_mode False) the shell
    keeps the client-side input items (never an id) and resets them on a fresh
    conversation."""
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="You are helpful")

    items = [
        {"type": "message", "role": "system", "content": []},
        {"type": "message", "role": "user", "content": []},
        {"type": "message", "role": "assistant", "content": []},
    ]
    # Simulate a completed stateless turn: the run loop stores the items and
    # never keeps an id to chain with.
    shell.conversation_turn = 0
    shell.conversation_items = items
    assert shell.conversation_items == items

    # F2 / "clear" call initialize_history -> fresh client-side history.
    shell.initialize_history(system_prompt="You are helpful")
    assert shell.conversation_items is None
    assert shell.conversation_turn == 0


def test_shell_rewind_completions_truncates_history_and_drops_recorded_turn():
    """/rewind in Completions mode truncates messages_history back to the
    last recorded turn start and drops that recorded start, so the rewound
    turn no longer counts: the pre-prompt rule derives Turn N from
    history_turns (issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    # Two completed turns: (hello/hi) then (again/ok). The recorded start
    # before the second turn is row 3 (system + hello + hi).
    shell.messages_history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "again"},
        {"role": "assistant", "content": "ok"},
    ]
    shell.history_turns = [1, 3]

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    # Rewound to the second turn's start (system + hello + hi).
    assert shell.messages_history == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    # The rewound turn's recorded start is gone: only one turn left.
    assert shell.history_turns == [1]


def test_shell_rewind_completions_at_turn_reports_nothing(capsys):
    """A /rewind with nothing to undo (history already truncated exactly at
    the last turn start) reports so and leaves the recorded turns untouched
    (issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    # History is exactly the recorded turn start: nothing to undo.
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.conversation_items = None
    shell.response_chain = []
    shell.response_turn = 0
    shell.previous_response_id = None

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    # State is preserved: no truncation, no recorded turn dropped.
    assert shell.messages_history == [{"role": "system", "content": "sys"}]
    assert shell.history_turns == [1]
    assert "Nothing to rewind" in capsys.readouterr().out


def test_shell_rewind_truncates_stateless_conversation_items():
    """/rewind truncates the client-side items back to the turn for
    stateless Responses providers and drops the recorded turn start, so the
    rewound turn no longer counts (issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    # Fresh conversation: system + user + assistant.
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.previous_response_id = None
    shell.conversation_turn = 2
    shell.conversation_items = [
        {"type": "message", "role": "system", "content": []},
        {"type": "message", "role": "user", "content": []},
        {"type": "message", "role": "assistant", "content": []},
    ]

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    # Rewound to the turn (system + user only).
    assert shell.conversation_items == [
        {"type": "message", "role": "system", "content": []},
        {"type": "message", "role": "user", "content": []},
    ]
    # The rewound turn's recorded start is gone.
    assert shell.history_turns == []


def test_shell_rewind_server_side_repoints_previous_response_id():
    """/rewind on a server-side Responses conversation (e.g. OpenAI) undoes
    the last completed turn by chaining the next turn (previous_response_id)
    from the response that preceded it, instead of resetting the whole
    server-side conversation to None (and drops the recorded turn start --
    issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    # Two completed turns: r1 then r2 (chained from r1). The recorded start
    # is before the second turn.
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.previous_response_id = "r2"
    shell.conversation_items = None
    shell.response_chain = ["r1", "r2"]
    shell.response_turn = 1

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    # The chain is truncated back to the recorded start and the next turn
    # chains from the response before the rewound exchange.
    assert shell.response_chain == ["r1"]
    assert shell.previous_response_id == "r1"
    # The rewound turn's recorded start is gone.
    assert shell.history_turns == []


def test_shell_rewind_server_side_single_turn_resets_to_fresh(capsys):
    """/rewind on a server-side Responses conversation with a single
    completed turn returns to a fresh server conversation (previous_response_id
    None), the same end state as the previous full reset for that case (and
    the recorded turn start is dropped -- issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.previous_response_id = "r1"
    shell.conversation_items = None
    shell.response_chain = ["r1"]
    shell.response_turn = 0

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    assert shell.response_chain == []
    assert shell.previous_response_id is None
    assert shell.history_turns == []
    assert "fresh conversation" in capsys.readouterr().out


def test_shell_rewind_server_side_at_turn_reports_nothing(capsys):
    """A second consecutive /rewind on a server-side conversation (already at
    the turn) reports nothing to rewind and keeps the conversation
    instead of resetting it (and leaves the recorded turns untouched --
    issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.previous_response_id = "r1"
    shell.conversation_items = None
    shell.response_chain = ["r1"]
    shell.response_turn = 1

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    # State is preserved: no truncation, no reset.
    assert shell.response_chain == ["r1"]
    assert shell.previous_response_id == "r1"
    assert shell.history_turns == [1]
    assert "Nothing to rewind" in capsys.readouterr().out


def test_shell_rewind_server_side_without_chain_falls_back_to_reset(capsys):
    """/rewind on a server-side conversation with no tracked chain (e.g. a
    manually seeded previous_response_id) keeps the legacy full-reset
    behaviour (and drops the recorded turn start -- issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.previous_response_id = "r1"
    shell.conversation_items = None
    shell.response_chain = []
    shell.response_turn = 0

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    assert shell.previous_response_id is None
    assert shell.history_turns == []
    assert "server-side conversation reset" in capsys.readouterr().out


def test_shell_run_turn_records_server_side_response_chain():
    """Each completed server-side Responses turn appends its final response id
    to the shell's response_chain, so /rewind has a rewind target (and a
    second turn appends the next id, keeping the chain in turn order)."""
    from janito.llm_clients.openai.conversations_api import ConversationResult
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    calls = {"n": 0}

    def turn_func(user_input, **kwargs):
        calls["n"] += 1
        return ConversationResult(content="hi", response_id=f"r{calls['n']}", input_items=None)

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("first")
    assert shell.response_chain == ["r1"]
    assert shell.previous_response_id == "r1"

    # The second turn is chained from the first response and appends its own.
    shell._run_turn("second")
    assert shell.response_chain == ["r1", "r2"]
    assert shell.previous_response_id == "r2"


def test_shell_run_turn_mirrors_server_side_turns_for_history():
    """Each completed server-side Responses turn appends its display-only
    mirror (user prompt + assistant text, Responses input items) to the
    shell's mirrored_history, so /history can render the conversation even
    though the real history lives on the server."""
    from janito.llm_clients.openai.conversations_api import ConversationResult
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    calls = {"n": 0}

    def turn_func(user_input, **kwargs):
        calls["n"] += 1
        return ConversationResult(
            content=f"reply {calls['n']}",
            response_id=f"r{calls['n']}",
            input_items=None,
            turn_items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_input}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"reply {calls['n']}"}],
                },
            ],
        )

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("first")
    assert len(shell.mirrored_history) == 2
    assert shell.mirrored_history[0]["content"][0]["text"] == "first"
    assert shell.mirrored_history[1]["content"][0]["text"] == "reply 1"

    # A second turn appends its own mirror items, in turn order.
    shell._run_turn("second")
    assert len(shell.mirrored_history) == 4
    assert shell.mirrored_history[2]["content"][0]["text"] == "second"
    assert shell.mirrored_history[3]["content"][0]["text"] == "reply 2"


def test_shell_run_turn_stateless_does_not_mirror():
    """Stateless Responses (e.g. DeepSeek) mirrors through
    conversation_items, so the /history display mirror stays empty."""
    from janito.llm_clients.openai.conversations_api import ConversationResult
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")

    def turn_func(user_input, **kwargs):
        return ConversationResult(
            content="ok",
            response_id=None,
            input_items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_input}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                },
            ],
            turn_items=[],
        )

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("hello")
    assert shell.mirrored_history == []
    assert len(shell.conversation_items) == 2
    assert shell.previous_response_id is None


def test_shell_rewind_server_side_truncates_mirrored_history():
    """/rewind on a server-side Responses conversation also truncates the
    display-only /history mirror back to its recorded start, so /history no
    longer shows the rewound exchange (and drops the recorded turn start --
    issue #78)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.history_turns = [1]
    shell.previous_response_id = "r2"
    shell.conversation_items = None
    shell.response_chain = ["r1", "r2"]
    shell.response_turn = 1
    shell.mirrored_history = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "one"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "reply 1"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "two"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "reply 2"}],
        },
    ]
    shell.mirrored_turn = 2

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    assert shell.response_chain == ["r1"]
    assert shell.previous_response_id == "r1"
    assert shell.mirrored_history == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "one"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "reply 1"}],
        },
    ]
    # The rewound turn's recorded start is gone.
    assert shell.history_turns == []


def test_shell_run_turn_keeps_chain_on_enter_cancel():
    """An Enter-cancelled server-side turn (RequestCancelled) appends nothing
    to the response_chain: the shell keeps chaining from the last completed
    response."""
    from janito.llm_clients import RequestCancelled
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    shell.response_chain = ["r1"]
    shell.response_turn = 1
    shell.previous_response_id = "r1"

    def turn_func(user_input, **kwargs):
        raise RequestCancelled("cancelled by Enter")

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("hello")

    # No completed turn: the chain and recorded start are unchanged.
    assert shell.response_chain == ["r1"]
    assert shell.previous_response_id == "r1"


def test_shell_initialize_history_resets_response_chain():
    """A fresh conversation (F2 / clear / provider switch) also clears the
    tracked server-side response chain so the next turn starts a new server
    conversation."""
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    shell.response_chain = ["r1", "r2"]
    shell.response_turn = 1

    shell.initialize_history(system_prompt="sys")
    assert shell.response_chain == []
    assert shell.response_turn == 0


def test_run_stream_round_recovers_response_id_on_cancel(monkeypatch):
    """Enter-cancel (RequestCancelled) carries the conversation state so the
    shell can continue without losing the user's message: server-side
    conversations hand back the pending user messages (the aborted response
    id is discarded by the provider and must NOT be chained from), stateless
    conversations pass back the full client-side items (which include the
    cancelled message)."""
    from janito.llm_clients import RequestCancelled

    # Server-side: the pending user messages are handed back for the caller
    # to re-send chained from the last completed response id; the aborted
    # response id from the partial stream is never attached.
    pending = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "List files"}],
        }
    ]
    exc = RequestCancelled("cancelled")
    exc.partial_result = ("", None, [], None, "resp_aborted")
    # The runner is a UI-side concern injected through the UIConfig (a
    # fake runner that raises the cancelled request).
    client = api.ResponsesClient(
        make_config(api_type="Responses"),
        make_ui_config(stream_runner=mock.Mock(side_effect=exc)),
    )

    with pytest.raises(RequestCancelled) as excinfo:
        client._run_stream_round(
            mock.Mock(),
            {},
            [],
            {
                "stateless_mode": False,
                "response_id": "r1",
                "input_items": "List files",
                "pending_items": pending,
            },
            base_url="https://api.example.com",
            api_key="sk-test",  # pragma: allowlist secret
            model="gpt-4o",
        )
    # No aborted response id: the next turn keeps chaining from the last
    # completed response ("r1").
    assert getattr(excinfo.value, "response_id", None) is None
    # The pending user messages are handed back so they are re-sent.
    assert excinfo.value.conversation_items == pending

    # Server-side without explicit pending items: a string prompt is wrapped
    # into a user message item so the shell can re-send it.
    exc3 = RequestCancelled("cancelled")
    exc3.partial_result = ("", None, [], None, "resp_aborted")
    client3 = api.ResponsesClient(
        make_config(api_type="Responses"),
        make_ui_config(stream_runner=mock.Mock(side_effect=exc3)),
    )

    with pytest.raises(RequestCancelled) as excinfo3:
        client3._run_stream_round(
            mock.Mock(),
            {},
            [],
            {
                "stateless_mode": False,
                "response_id": None,
                "input_items": "List files",
            },
            base_url="https://api.example.com",
            api_key="sk-test",  # pragma: allowlist secret
            model="gpt-4o",
        )
    assert getattr(excinfo3.value, "response_id", None) is None
    assert excinfo3.value.conversation_items == pending

    # Stateless: the full client-side items (system + cancelled message) are
    # handed back so the next turn re-sends them; no id to chain with.
    items = [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": "Sys"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "List files"}],
        },
    ]
    exc2 = RequestCancelled("cancelled")
    exc2.partial_result = ("", None, [], None, "resp_x")
    client2 = api.ResponsesClient(
        make_config(api_type="Responses"),
        make_ui_config(stream_runner=mock.Mock(side_effect=exc2)),
    )

    with pytest.raises(RequestCancelled) as excinfo2:
        client2._run_stream_round(
            mock.Mock(),
            {},
            [],
            {
                "stateless_mode": True,
                "response_id": None,
                "input_items": items,
            },
            base_url="https://api.example.com",
            api_key="sk-test",  # pragma: allowlist secret
            model="gpt-4o",
        )
    assert getattr(excinfo2.value, "response_id", None) is None
    assert excinfo2.value.conversation_items == items


def test_shell_run_turn_records_history_turns():
    """Every _run_turn records the turn's start (the history length before
    the turn) in shell.history_turns, so /history can mark where each turn
    started and /rewind can step back one turn at a time."""
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    assert shell.history_turns == []

    seen = []

    def turn_func(user_input, **kwargs):
        seen.append(len(kwargs["previous_messages"]))
        kwargs["previous_messages"].append({"role": "user", "content": user_input})
        kwargs["previous_messages"].append({"role": "assistant", "content": "ok"})
        return "ok"

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("one")
    shell._run_turn("two")

    # History: [sys] -> turn one -> [sys, one, ok] -> turn two -> [sys, one, ok, two, ok]
    assert shell.history_turns == [1, 3]
    assert seen == [1, 3]


def test_shell_run_turn_error_propagates(capsys):
    """Unexpected turn errors propagate instead of being swallowed."""
    import pytest

    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")

    def turn_func(user_input, **kwargs):
        kwargs["previous_messages"].append({"role": "user", "content": user_input})
        kwargs["previous_messages"].append({"role": "assistant", "content": "partial"})
        raise RuntimeError("boom")

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    with pytest.raises(RuntimeError, match="boom"):
        shell._run_turn("hello")


def test_shell_rewind_steps_back_one_turn_at_a_time(capsys):
    """/rewind undoes the most recent turn (truncating back to the last
    turn and dropping it), so consecutive rewinds step back one turn
    at a time through the turn list."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    shell.messages_history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": "r2"},
    ]
    shell.history_turns = [1, 3]

    handler = RewindCmdHandler()
    handler._do_rewind(shell)
    assert [m["content"] for m in shell.messages_history] == ["sys", "one", "r1"]
    assert shell.history_turns == [1]

    handler._do_rewind(shell)
    assert [m["content"] for m in shell.messages_history] == ["sys"]
    assert shell.history_turns == []

    # Nothing left to rewind via the messages history.
    handler._do_rewind(shell)
    assert [m["content"] for m in shell.messages_history] == ["sys"]
    assert "Nothing to rewind" in capsys.readouterr().out


def test_shell_run_turn_records_stateless_turn_position():
    """Stateless Responses: the recorded start is the number of rows /history
    would render (the conversation_items length), not len(messages_history)
    -- messages_history only ever holds the system prompt, so using its
    length would pile every marker at the same position."""
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    # One completed stateless turn lives in conversation_items (system +
    # user + assistant), while messages_history still only holds the prompt.
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.conversation_items = [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": "sys"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "one"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "r1"}],
        },
    ]

    def turn_func(user_input, **kwargs):
        return "ok"

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("two")

    # The recorded start marks the row the next user message will occupy (3),
    # so /history shows the marker before "two", not after the system row.
    assert shell.history_turns == [3]


def test_shell_run_turn_records_server_side_turn_position():
    """Server-side Responses: the recorded start is the sum of the rows
    /history renders (messages_history + mirrored_history + pending items),
    so each marker lands before its own user message."""
    from janito.shell import InteractiveShell

    shell = InteractiveShell(model="test-model", no_history=True)
    shell.initialize_history(system_prompt="sys")
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.previous_response_id = "r1"
    shell.response_chain = ["r1"]
    # One completed server-side turn mirrored client-side (user + assistant).
    shell.mirrored_history = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "one"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "r1"}],
        },
    ]

    def turn_func(user_input, **kwargs):
        return "ok"

    shell.turn_func = turn_func
    shell.verbose = False
    shell.no_tools = True
    shell.thinking = False

    shell._run_turn("two")

    # rows = system(1) + mirrored(2) = 3 -> marker before "two".
    assert shell.history_turns == [3]


def test_shell_rewind_stateless_pops_turn_for_marker_sync():
    """/rewind on a stateless Responses conversation also drops the last
    history turn, so /history markers stay in sync with the truncated
    rows (no stale marker at the rewound turn's old position)."""
    from janito.shell.cmds.rewind import RewindCmdHandler

    shell = RewindCmdHandler.__new__(RewindCmdHandler)
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.previous_response_id = None
    shell.history_turns = [1, 3]
    shell.conversation_turn = 3
    shell.conversation_items = [
        {"type": "message", "role": "system", "content": []},
        {"type": "message", "role": "user", "content": []},
        {"type": "message", "role": "assistant", "content": []},
        {"type": "message", "role": "user", "content": []},
        {"type": "message", "role": "assistant", "content": []},
    ]

    handler = RewindCmdHandler()
    handler._do_rewind(shell)

    assert len(shell.conversation_items) == 3
    assert shell.history_turns == [1]
