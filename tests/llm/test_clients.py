"""
Tests for the shared Client base class and its four concrete subclasses.

The module-level ``run_turn`` functions of ``completions_api``,
``conversations_api``, ``anthropic_api`` and ``dashscope_api`` now delegate to
``*Client`` subclasses of ``janito.llm_clients.base_client.Client``.  These
tests pin the new class contract:

- The base class raises ``NotImplementedError`` for unimplemented hooks.
- Each subclass declares the right ``api_type`` / ``backend_default``.
- The per-turn hooks preserve the historical behaviour (e.g. the "is not
  None" empty-list semantics of ``previous_messages``, the Responses state
  dict, and the 4-tuple model-settings shape for the native-SDK clients).

The behavioural equivalence of the four ``run_turn`` functions is covered
by the existing client tests (``test_conversations_api``,
``test_anthropic_api``, ``test_dashscope_api``, ``test_reasoning_effort``),
which monkeypatch the module globals that the subclasses forward to.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from conftest import make_config, make_ui_config

from janito.llm_clients.base_client import Client

if pytest is not None:
    # ---- base class contract -------------------------------------------

    def test_base_hooks_raise_not_implemented():
        c = Client(make_config())
        # (hook, args) -- each hook must raise NotImplementedError when the
        # base implementation is reached (before any argument validation).
        # ``_resolve_model_settings`` has a base default (it reads the
        # resolved APIConfig), so it is not in this list.
        hooks = {
            "_create_sdk_client": ("http://example.test", "dummy-key"),
            "_create_tool_executor": (None,),
            "_resolve_tools": (None, []),
            "_init_conversation_state": ("hi", "openai", "gpt-4"),
            "_build_call_kwargs": ("m", {}, 1000, None, None, False),
            "_run_stream_round": (
                None,
                {},
                [],
                {},
            ),
            "_handle_tool_calls": ({}, "", None, {}, None),
            "_finalize": ("", None, {}),
        }
        # _run_stream_round has keyword-only params after ``state``.
        with pytest.raises(NotImplementedError):
            c._run_stream_round(
                None,
                {},
                [],
                {},
                base_url=None,
                api_key="dummy-key",  # pragma: allowlist secret
                model="m",
            )
        del hooks["_run_stream_round"]
        for hook, args in hooks.items():
            with pytest.raises(NotImplementedError):
                getattr(c, hook)(*args)

    def test_base_model_settings_default():
        """The base Client resolves the settings from the resolved APIConfig.

        The four-value shape is the shared default; subclasses override only
        when their API drops or transforms one of the values (e.g. DashScope
        drops reasoning_effort).
        """
        c = Client(
            make_config(
                max_output_tokens=64000,
                max_input_tokens=200000,
                reasoning_effort="high",
                thinking=True,
            )
        )
        thinking, max_out, max_in, reasoning = c._resolve_model_settings("openai", "gpt-4")
        assert (thinking, max_out, max_in, reasoning) == (True, 64000, 200000, "high")

    # ---- concrete subclasses: identity ----------------------------------

    def test_subclass_identities():
        from janito.llm_clients.anthropic.anthropic_api import AnthropicClient
        from janito.llm_clients.dashscope.dashscope_api import DashScopeClient
        from janito.llm_clients.openai.completions_api import CompletionsClient
        from janito.llm_clients.openai.conversations_api import ResponsesClient

        assert issubclass(CompletionsClient, Client)
        assert issubclass(ResponsesClient, Client)
        assert issubclass(AnthropicClient, Client)
        assert issubclass(DashScopeClient, Client)

        assert CompletionsClient(make_config()).api_type == "Completions"
        assert ResponsesClient(make_config(api_type="Responses")).api_type == "Responses"
        assert AnthropicClient(make_config(api_type="Anthropic")).api_type == "Anthropic"
        assert DashScopeClient(make_config(api_type="DashScope")).api_type == "DashScope"

        assert AnthropicClient(make_config(api_type="Anthropic")).backend_default == "https://api.anthropic.com"
        assert (
            DashScopeClient(make_config(api_type="DashScope")).backend_default
            == "https://dashscope-intl.aliyuncs.com/api/v1"
        )

    # ---- conversation-state semantics -----------------------------------

    def test_completions_state_preserves_empty_list():
        """An empty caller-owned history must be kept (not replaced)."""
        from janito.llm_clients.openai.completions_api import CompletionsClient

        c = CompletionsClient(make_config())
        history: list = []
        state = c._init_conversation_state("hi", "openai", "gpt-4", previous_messages=history)
        # The same list object is used and the user turn is appended to it.
        assert state is history
        assert state == [{"role": "user", "content": "hi"}]

    def test_completions_state_none_starts_fresh():
        from janito.llm_clients.openai.completions_api import CompletionsClient

        c = CompletionsClient(make_config())
        state = c._init_conversation_state("hi", "openai", "gpt-4", previous_messages=None)
        assert state == [{"role": "user", "content": "hi"}]

    def test_anthropic_state_keeps_system_parameter():
        """The top-level system parameter is resolved from instructions and
        the in-place history keeps the system-role message."""
        from janito.llm_clients.anthropic.anthropic_api import AnthropicClient

        c = AnthropicClient(make_config(api_type="Anthropic"))
        history = [{"role": "system", "content": "Be helpful"}]
        state = c._init_conversation_state(
            "hi",
            "anthropic",
            "claude-sonnet-5",
            previous_messages=history,
            instructions=None,
        )
        assert state["messages"] is history
        assert state["messages"][-1] == {"role": "user", "content": "hi"}
        # The system message is preserved in the client-side history and
        # surfaced as the top-level system parameter.
        assert state["messages"][0] == {"role": "system", "content": "Be helpful"}
        assert state["system"] == "Be helpful"

    def test_responses_state_dict_shape():
        from janito.llm_clients.openai.conversations_api import ResponsesClient

        c = ResponsesClient(make_config(api_type="Responses"))
        state = c._init_conversation_state(
            "hi",
            "openai",
            "gpt-6-luna",
            previous_response_id=None,
            previous_items=None,
            instructions="Be helpful",
        )
        assert state["stateless_mode"] is False
        assert state["response_id"] is None
        assert state["conversation_items"] is None
        assert state["input_items"] == "hi"
        assert state["instructions"] == "Be helpful"
        assert state["message_count"] == 1

    def test_dashscope_state_prepends_instructions():
        from janito.llm_clients.dashscope.dashscope_api import DashScopeClient

        c = DashScopeClient(make_config(api_type="DashScope"))
        state = c._init_conversation_state(
            "hi",
            "alibaba",
            "qwen3.8-max",
            previous_messages=None,
            instructions="be terse",
        )
        assert state == [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ]

    # ---- model-settings shape for the native-SDK clients ----------------

    def test_anthropic_model_settings_returns_4_tuple():
        """The hook passes the config's token limits and thinking through."""
        from janito.llm_clients.anthropic import anthropic_api

        config = make_config(
            api_type="Anthropic",
            max_output_tokens=64000,
            max_input_tokens=200000,
            reasoning_effort=None,
        )
        c = anthropic_api.AnthropicClient(config)
        thinking, max_out, max_in, reasoning = c._resolve_model_settings("anthropic", "claude-sonnet-5")
        # thinking comes from the resolved config (make_config defaults it
        # to False).
        assert thinking is False
        assert max_out == 64000
        assert max_in == 200000
        # reasoning_effort is accepted but not used by the native SDK.
        assert reasoning is None

    def test_anthropic_model_settings_config_override_wins():
        """The resolved config value is passed through unchanged -- no
        config-store read in the hook."""
        from janito.llm_clients.anthropic import anthropic_api

        config = make_config(
            api_type="Anthropic",
            max_output_tokens=64000,
            max_input_tokens=4096,
            reasoning_effort=None,
        )
        c = anthropic_api.AnthropicClient(config)
        _, _, max_in, _ = c._resolve_model_settings("anthropic", "claude-sonnet-5")
        assert max_in == 4096

    def test_dashscope_model_settings_returns_4_tuple():
        import janito.llm_clients.dashscope.dashscope_api as dsa

        config = make_config(
            api_type="DashScope",
            max_output_tokens=8192,
            max_input_tokens=128000,
            reasoning_effort="xhigh",
            thinking=True,
        )
        c = dsa.DashScopeClient(config)
        thinking, max_out, max_in, reasoning = c._resolve_model_settings("alibaba", "qwen3.8-max")
        assert (thinking, max_out, max_in) == (True, 8192, 128000)
        # reasoning_effort is dropped (not used by the native SDK).
        assert reasoning is None

    # ---- pipeline wiring through module globals -------------------------

    # ---- verbose API call/response output -------------------------------

    def test_print_verbose_api_call_shows_messages_tail_only():
        """The request dump replaces the full messages list with its tail."""
        from io import StringIO

        from rich.console import Console

        from janito.ui.display import _print_verbose_api_call

        out = StringIO()
        console = Console(file=out, width=120, force_terminal=True)
        long_history = [
            {"role": "user", "content": "very early message, should not appear"},
            {"role": "assistant", "content": "early answer, should not appear"},
            {"role": "user", "content": "middle message, should not appear"},
            {"role": "user", "content": "fourth message, shown"},
            {"role": "user", "content": "penultimate message"},
            {"role": "assistant", "content": "tail message " + "x" * 1000},
        ]
        call_kwargs = {
            "model": "gpt-4",
            "messages": long_history,
            "temperature": 1.0,
            "max_completion_tokens": 8192,
        }
        _print_verbose_api_call(console, call_kwargs, tools_schemas=[])

        rendered = out.getvalue()
        # The summary notes the total count and that only the tail is shown.
        assert "6 items (showing last 3)" in rendered
        # The tail messages are present (truncated), the early ones are not.
        assert "tail message" in rendered
        assert "penultimate message" in rendered
        assert "fourth message" in rendered
        assert "very early message" not in rendered
        assert "early answer" not in rendered
        assert "middle message" not in rendered
        # Long content is truncated instead of dumped in full.
        assert "more chars" in rendered
        assert "x" * 1000 not in rendered
        # The scalar parameters survive untouched.
        assert '"max_completion_tokens": 8192' in rendered

    def test_print_verbose_api_call_summarizes_tools():
        from io import StringIO

        from rich.console import Console

        from janito.ui.display import _print_verbose_api_call

        out = StringIO()
        console = Console(file=out, width=120, force_terminal=True)
        call_kwargs = {"model": "gpt-4", "input": "hello"}
        _print_verbose_api_call(
            console,
            call_kwargs,
            tools_schemas=[
                {"type": "function", "function": {"name": "list_files"}},
                {"type": "function", "function": {"name": "read_file"}},
            ],
        )
        rendered = out.getvalue()
        assert '"2 tools"' in rendered
        assert '"list_files"' in rendered
        assert '"read_file"' in rendered

    def test_print_verbose_api_response_summary():
        from io import StringIO
        from types import SimpleNamespace

        from rich.console import Console

        from janito.ui.display import _print_verbose_api_response

        out = StringIO()
        console = Console(file=out, width=120, force_terminal=True)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        _print_verbose_api_response(
            console,
            full_content="final answer " + "y" * 1000,
            reasoning_content="thinking step",
            tool_calls=[
                {"name": "list_files", "arguments": '{"path": "."}'},
                {"name": "read_file", "arguments": "{}"},
            ],
            usage_info=usage,
            response_id="resp_1",
            raw_attrs={
                "id": "chatcmpl-1",
                "model": "gpt-4o",
                "created": 1720000000,
                "system_fingerprint": "fp_abc",
                "finish_reason": "stop",
            },
        )
        rendered = out.getvalue()
        assert "Content:" in rendered
        assert "Reasoning:" in rendered
        assert "thinking step" in rendered
        assert "Tool calls: list_files(" in rendered
        assert "read_file(" in rendered
        assert "Usage:" in rendered
        assert "Response id: resp_1" in rendered
        # All raw top-level response attributes are enumerated.
        assert "Raw id: chatcmpl-1" in rendered
        assert "Raw model: gpt-4o" in rendered
        assert "Raw created: 1720000000" in rendered
        assert "Raw system_fingerprint: fp_abc" in rendered
        assert "Raw finish_reason: stop" in rendered
        # Long content is truncated (not the full 1000-char tail dumped).
        assert "more chars" in rendered
        assert "y" * 1000 not in rendered

    def test_verbose_wiring_in_send(monkeypatch):
        """verbose=True routes the API call params + response summary through
        the injected TurnObserver; verbose=False emits neither verbose event."""
        import janito.llm_clients.openai.completions_api as ca

        class FakeObserver:
            def __init__(self):
                self.events = []

            def on_verbose_info(self, **kwargs):
                self.events.append("info")

            def on_verbose_call(self, call_kwargs, tools_schemas):
                self.events.append("call")

            def on_verbose_response(self, *args, **kwargs):
                self.events.append("response")

            def on_reasoning(self, content):
                pass

            def on_message(self, content):
                pass

            def on_turn_complete(self, token_stats, api_config):
                pass

        def fake_run(func, client, call_kwargs, tools_schemas):
            return "hi", None, {}, None, {"id": "chatcmpl-1"}

        monkeypatch.setattr(
            "janito.llm_clients.client_support._load_mcp",
            lambda use_mcp: (None, []),
        )

        # A fake runner and a capturing observer are injected through the
        # UIConfig (the UI-side stream runner and the turn observer are no
        # longer constructor params / module globals to monkeypatch).
        observer = FakeObserver()
        client = ca.CompletionsClient(
            make_config(model="gpt-4", use_mcp=False),
            make_ui_config(stream_runner=fake_run, observer=observer),
        )

        client.run_turn("hello", verbose=True, tools=[])
        assert observer.events == ["info", "call", "response"]

        observer.events.clear()
        client.run_turn("hello", verbose=False, tools=[])
        assert observer.events == []

    def test_verbose_responses_response_id_from_state(monkeypatch):
        """The Responses client's state dict carries the response id into the
        verbose response summary (server-side conversations chain by id)."""
        import janito.llm_clients.openai.conversations_api as ca

        captured = {}

        class FakeObserver:
            def on_verbose_response(self, *args, **kwargs):
                captured["response_id"] = args[4]

            def on_verbose_info(self, **kwargs):
                pass

            def on_verbose_call(self, call_kwargs, tools_schemas):
                pass

            def on_reasoning(self, content):
                pass

            def on_message(self, content):
                pass

            def on_turn_complete(self, token_stats, api_config):
                pass

        def fake_run(func, client, call_kwargs, tools_schemas):
            return (
                "hi",
                None,
                {},
                None,
                "resp_99",
                {"id": "resp_99", "status": "completed"},
                [],
                [],
                [],
            )

        monkeypatch.setattr(
            "janito.llm_clients.client_support._load_mcp",
            lambda use_mcp: (None, []),
        )
        monkeypatch.setattr(
            ca,
            "_init_conversation_state",
            lambda provider, model, previous_response_id, previous_items, instructions, prompt: (
                False,
                None,
                None,
                prompt,
                [],
            ),
        )
        monkeypatch.setattr(
            ca,
            "_build_call_kwargs",
            lambda *a, **k: {"model": "gpt-4o", "input": "hello"},
        )

        client = ca.ResponsesClient(
            make_config(api_type="Responses", model="gpt-4o", use_mcp=False),
            make_ui_config(stream_runner=fake_run, observer=FakeObserver()),
        )

        result = client.run_turn("hello", verbose=True, tools=[])
        assert result.response_id == "resp_99"
        # run_turn() extracts the server-side response id from the Responses
        # state dict and hands it to the observer's on_verbose_response.
        assert captured["response_id"] == "resp_99"

    # ---- error classification (native-SDK clients) ----------------------

    def test_classify_error_recognizes_not_found_payloads():
        from janito.llm_clients.client_support import _classify_error

        assert _classify_error(Exception("Model not exist: `gpt-4`")) == "not_found"
        assert _classify_error(Exception("model not found")) == "not_found"
        assert _classify_error(Exception("previous response id not found")) == "not_found"

    def test_classify_error_recognizes_auth_payloads():
        from janito.llm_clients.client_support import _classify_error

        # 401 status code (Anthropic / DashScope style).
        e = Exception("401 invalid api key")
        e.status_code = 401
        assert _classify_error(e) == "auth"

        # 401 error code (google-genai style, no status_code adaptation).
        e = Exception("boom")
        e.code = 401
        assert _classify_error(e) == "auth"

        # InvalidApiKey error code string.
        e = Exception("boom")
        e.code = "InvalidApiKey"
        assert _classify_error(e) == "auth"

    def test_classify_error_unknown_failure():
        from janito.llm_clients.client_support import _classify_error

        assert _classify_error(Exception("502 upstream timeout")) == "unknown"

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        import tempfile

        class _MP:
            def __init__(self):
                self._undo = []

            def setattr(self, obj, name, value):
                self._undo.append((obj, name, getattr(obj, name)))
                setattr(obj, name, value)

            def restore(self):
                for obj, name, value in reversed(self._undo):
                    setattr(obj, name, value)

        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                mp = _MP()
                try:
                    import inspect

                    params = inspect.signature(fn).parameters
                    with tempfile.TemporaryDirectory():
                        if "monkeypatch" in params:
                            fn(mp)
                        else:
                            fn()
                finally:
                    mp.restore()
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
