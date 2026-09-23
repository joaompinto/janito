"""Web agent Responses API-type tests.

Split from ``test_web_api_types.py`` (call-kwargs builders and
accumulators for the Responses runner).
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
# Responses runner
# ---------------------------------------------------------------------------


def _cfg(thinking=False):
    class _Cfg:
        effective_thinking = thinking

        def effective_tools_for(self, api_type):
            return None

    return _Cfg()


def test_responses_build_call_kwargs_converts_history_and_tools():
    from janito.llm_adapters import responses

    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hello"},
    ]
    tools = [
        {
            "type": "function",
            "function": {"name": "ReadFile", "description": "read", "parameters": {}},
        }
    ]
    kwargs = responses.build_call_kwargs("gpt-4", messages, tools, _cfg(thinking=True), 1000, None, "high")
    assert kwargs["model"] == "gpt-4"
    assert kwargs["max_output_tokens"] == 1000
    assert kwargs["reasoning"] == {"effort": "high"}
    assert kwargs["extra_body"]["enable_thinking"] is True
    assert kwargs["stream"] is True

    # The full history is re-sent as Responses input items.
    assert kwargs["input"] == [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": "Be helpful."}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}],
        },
    ]
    # Tools are converted to the Responses top-level shape.
    assert kwargs["tools"] == [
        {
            "type": "function",
            "name": "ReadFile",
            "description": "read",
            "parameters": {},
        }
    ]
    assert kwargs["tool_choice"] == "auto"


def test_responses_build_call_kwargs_omits_optional_fields():
    from janito.llm_adapters import responses

    kwargs = responses.build_call_kwargs(
        "gpt-4",
        [{"role": "user", "content": "hi"}],
        None,
        _cfg(thinking=False),
        None,
        None,
        None,
    )
    assert "max_output_tokens" not in kwargs
    assert "reasoning" not in kwargs
    assert "extra_body" not in kwargs
    assert "tools" not in kwargs


def test_responses_build_call_kwargs_passes_structured_thinking_dict():
    """A structured thinking default (MiniMax-M3 {'type': 'adaptive'}) is sent
    through as extra_body thinking instead of enable_thinking."""
    from janito.llm_adapters import responses

    kwargs = responses.build_call_kwargs(
        "MiniMax-M3",
        [{"role": "user", "content": "hi"}],
        None,
        _cfg(thinking={"type": "adaptive"}),
        1000,
        None,
        None,
    )
    assert kwargs["extra_body"]["thinking"] == {"type": "adaptive"}
    assert "enable_thinking" not in kwargs["extra_body"]


def test_responses_build_call_kwargs_appends_builtin_tools():
    """The effective model's built-in tools (e.g. Alibaba/Qwen's
    code_interpreter / web_search / web_extractor) are appended to the
    Responses tools array alongside any function tools."""
    from janito.llm_adapters import responses

    tools = [
        {
            "type": "function",
            "function": {"name": "ReadFile", "description": "read", "parameters": {}},
        }
    ]

    class _Cfg:
        effective_thinking = True

        def effective_tools_for(self, api_type):
            return [
                {"type": "code_interpreter"},
                {"type": "web_search"},
                {"type": "web_extractor"},
            ]

    kwargs = responses.build_call_kwargs(
        "qwen3.8-max",
        [{"role": "user", "content": "hi"}],
        tools,
        _Cfg(),
        1000,
        None,
        None,
    )
    assert kwargs["tools"] == [
        {
            "type": "function",
            "name": "ReadFile",
            "description": "read",
            "parameters": {},
        },
        {"type": "code_interpreter"},
        {"type": "web_search"},
        {"type": "web_extractor"},
    ]
    assert kwargs["tool_choice"] == "auto"


def test_responses_build_call_kwargs_appends_builtin_tools_without_function_tools():
    """Built-in tools are still enabled with no function tools (like
    image_generation for gpt-6)."""
    from janito.llm_adapters import responses

    class _Cfg:
        effective_thinking = True

        def effective_tools_for(self, api_type):
            return [{"type": "web_search"}]

    kwargs = responses.build_call_kwargs(
        "qwen3.8-max",
        [{"role": "user", "content": "hi"}],
        None,
        _Cfg(),
        1000,
        None,
        None,
    )
    assert kwargs["tools"] == [{"type": "web_search"}]
    assert kwargs["tool_choice"] == "auto"


def test_responses_build_call_kwargs_appends_image_generation_tool_for_gpt5():
    """Mainline gpt-6 models get the native ``image_generation`` tool."""
    from janito.llm_adapters import responses

    tools = [
        {
            "type": "function",
            "function": {"name": "ReadFile", "description": "read", "parameters": {}},
        }
    ]
    kwargs = responses.build_call_kwargs(
        "gpt-6-sol",
        [{"role": "user", "content": "draw a cat"}],
        tools,
        _cfg(thinking=False),
        None,
        None,
        None,
    )
    # Function tools are converted to the Responses top-level shape, then the
    # native image_generation tool is appended verbatim (it is not a function
    # schema and must not go through the conversion).
    assert kwargs["tools"] == [
        {
            "type": "function",
            "name": "ReadFile",
            "description": "read",
            "parameters": {},
        },
        {"type": "image_generation"},
    ]
    assert kwargs["tool_choice"] == "auto"


def test_responses_build_call_kwargs_skips_image_generation_tool_for_other_models():
    """Older / third-party models do not get the image_generation tool."""
    from janito.llm_adapters import responses

    tools = [
        {
            "type": "function",
            "function": {"name": "ReadFile", "description": "read", "parameters": {}},
        }
    ]
    kwargs = responses.build_call_kwargs(
        "gpt-4",
        [{"role": "user", "content": "hi"}],
        tools,
        _cfg(thinking=False),
        None,
        None,
        None,
    )
    assert kwargs["tools"] == [
        {
            "type": "function",
            "name": "ReadFile",
            "description": "read",
            "parameters": {},
        }
    ]
    # A non-gpt-5/gpt-6 model with no function tools gets no tools at all.
    kwargs = responses.build_call_kwargs(
        "gpt-4",
        [{"role": "user", "content": "hi"}],
        None,
        _cfg(thinking=False),
        None,
        None,
        None,
    )
    assert "tools" not in kwargs


def test_responses_build_call_kwargs_image_generation_tool_without_function_tools():
    """The native image_generation tool is enabled for gpt-6 even when no
    function tools are configured (it is a model capability, not a tool)."""
    from janito.llm_adapters import responses

    kwargs = responses.build_call_kwargs(
        "gpt-6-sol",
        [{"role": "user", "content": "draw a cat"}],
        None,
        _cfg(thinking=False),
        None,
        None,
        None,
    )
    assert kwargs["tools"] == [{"type": "image_generation"}]
    assert kwargs["tool_choice"] == "auto"


def test_responses_accumulator_folds_stream_events():
    from janito.llm_adapters.responses import ResponsesTurnAccumulator

    acc = ResponsesTurnAccumulator()
    events = [
        SimpleNamespace(type="response.created", response=SimpleNamespace(id="r1")),
        SimpleNamespace(type="response.reasoning_text.delta", delta="think"),
        SimpleNamespace(type="response.output_text.delta", delta="Hello"),
        SimpleNamespace(type="response.function_call_arguments.delta", item_id="fc1", delta='{"a"'),
        SimpleNamespace(
            type="response.function_call_arguments.done",
            item_id="fc1",
            arguments='{"a":1}',
        ),
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="function_call", call_id="call_1", name="ReadFile", id="fc1"),
        ),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(
                id="r1",
                usage=SimpleNamespace(total_tokens=9, input_tokens=5, output_tokens=4),
            ),
        ),
    ]
    deltas = [acc.handle(ev) for ev in events]
    assert acc.full_content() == "Hello"
    assert acc.reasoning_content() == "think"
    assert acc.tool_calls_list() == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "ReadFile", "arguments": '{"a":1}'},
        }
    ]
    from janito.web.backend.events import usage_event_from_usage

    usage = usage_event_from_usage(acc.usage_object(), max_tokens=100)
    assert (usage.last_input, usage.last_output, usage.total, usage.max_tokens) == (
        5,
        4,
        9,
        100,
    )
    # Reasoning/text deltas are surfaced live for the browser.
    assert deltas[1] == ("think", None)
    assert deltas[2] == (None, "Hello")


def test_responses_accumulator_raises_failed_error():
    from janito.llm_adapters.responses import ResponsesTurnAccumulator

    acc = ResponsesTurnAccumulator()
    with pytest.raises(RuntimeError, match="boom"):
        acc.handle(
            SimpleNamespace(
                type="response.failed",
                response=SimpleNamespace(error=SimpleNamespace(message="boom")),
            )
        )


def test_responses_accumulator_captures_image_generation_call():
    """image_generation_call output items are saved to temp PNG files."""
    import base64
    import os

    from janito.llm_adapters.responses import ResponsesTurnAccumulator

    # A tiny valid PNG (signature + junk payload is enough for the test).
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDRjunk"
    b64_data = base64.b64encode(png_bytes).decode()

    acc = ResponsesTurnAccumulator()
    acc.handle(
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(
                type="image_generation_call",
                id="img_1",
                result=b64_data,
                revised_prompt="A gray tabby cat hugging an otter",
            ),
        )
    )

    # No function-call tool turn is produced for a native image result.
    assert acc.tool_calls_list() == []
    assert len(acc.image_results) == 1
    img = acc.image_results[0]
    assert img["revised_prompt"] == "A gray tabby cat hugging an otter"
    # The saved file is a kept temp PNG in the system temp directory, ready
    # for the /api/images/ router to serve.
    assert os.path.isfile(img["path"])
    assert img["path"].endswith(".png")
    with open(img["path"], "rb") as fh:
        assert fh.read() == png_bytes
    os.remove(img["path"])


def test_responses_accumulator_ignores_invalid_image_generation_call():
    """A malformed image_generation_call result is skipped, not fatal."""
    import base64

    from janito.llm_adapters.responses import ResponsesTurnAccumulator

    acc = ResponsesTurnAccumulator()
    # Non-decodable base64 -> no image result, no crash.
    acc.handle(
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", id="img_1", result="!!!not-base64!!!"),
        )
    )
    assert acc.image_results == []
    # Missing result entirely -> no image result.
    acc.handle(
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(type="image_generation_call", id="img_2"),
        )
    )
    assert acc.image_results == []
    # Base64 that decodes to a non-PNG payload is still saved (the backend
    # serves it as image/png; the bytes are whatever the model produced).
    acc.handle(
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(
                type="image_generation_call",
                id="img_3",
                result=base64.b64encode(b"just some bytes").decode(),
            ),
        )
    )
    assert len(acc.image_results) == 1
