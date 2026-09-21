"""
Tests for reasoning-effort support in the OpenAI-compatible API calls.

Covers:
- ``run_turn`` resolving the reasoning level (CLI arg > per-provider config
  > built-in provider-config default) and sending it as ``reasoning_effort``.
- The web agent's ``build_call_kwargs`` forwarding ``reasoning_effort``.
- The CLI ``--reasoning-effort`` flag parsing.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from conftest import make_config, make_ui_config

import janito.config_dir as config_dir_mod
import janito.llm_clients.openai.completions_api as client_mod
from janito.auth_config import set_api_key
from janito.llm_adapters.completions import build_call_kwargs


@pytest.fixture(autouse=True)
def _isolate_config_dir(monkeypatch, tmp_path):
    """Point the config directory at a temp dir for every test.

    ``run_turn`` resolves the reasoning level / thinking from the
    per-provider config (``<provider>.reasoning-effort``), which lives in the
    real ``~/.janito`` by default, and ``build_api_config`` reads the auth
    store. Without this fixture tests would read/write the developer's actual
    config, making them order- and environment-dependent.
    """
    monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path)
    for _provider, _key in {
        "alibaba": "sk-test-alibaba",
        "openai": "sk-test-openai",
        "deepseek": "sk-test-deepseek",
        "minimax": "sk-test-minimax",
        "google": "sk-test-google",
    }.items():
        set_api_key(_provider, _key)


def _fake_run_returns(content, reasoning=None, tool_calls=None, usage=None):
    """Capture the call kwargs and return a canned streaming result."""

    def fake_run(func, client, call_kwargs, tools_schemas):
        fake_run.captured_kwargs = call_kwargs
        return content, reasoning, tool_calls or {}, usage, {}

    fake_run.captured_kwargs = None
    return fake_run


if pytest is not None:

    def test_run_turn_passes_builtin_default_reasoning_effort():
        """The resolved reasoning level (config carries alibaba's built-in
        xhigh default) is sent as reasoning_effort."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="alibaba",
            model="qwen3.8-max",
            reasoning_effort="xhigh",
            use_mcp=False,
        )
        result = client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert result == "hi"
        assert fake_run.captured_kwargs["reasoning_effort"] == "xhigh"

    def test_run_turn_cli_reasoning_effort_overrides_default():
        """The config's resolved reasoning level (--reasoning-effort low) wins
        over the built-in xhigh default."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="alibaba",
            model="qwen3.8-max",
            reasoning_effort="low",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))
        assert fake_run.captured_kwargs["reasoning_effort"] == "low"

    def test_run_turn_config_reasoning_effort_used(monkeypatch, tmp_path):
        """A per-provider config value resolves through build_api_config when
        no CLI arg is given."""
        from janito.config_cli import set_config_from_cli
        from janito.llm_clients.api_config import build_api_config

        set_api_key("alibaba", "sk-test")
        # Scope the value to qwen3.8-max: the config key is model-scoped
        # (both Qwen models declare reasoning levels).
        set_config_from_cli("reasoning-effort=medium", "alibaba", "qwen3.8-max")
        fake_run = _fake_run_returns("hi")
        config = build_api_config(
            api_type="Completions",
            cli_provider="alibaba",
            cli_model="qwen3.8-max",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert fake_run.captured_kwargs["reasoning_effort"] == "medium"

    def test_run_turn_no_reasoning_effort_omits_effort():
        """No reasoning_effort is sent when nothing resolves (e.g. openai)."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="openai",
            model="gpt-4",
            reasoning_effort=None,
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert "reasoning_effort" not in fake_run.captured_kwargs

    def test_run_turn_thinking_defaults_on_for_deepseek():
        """DeepSeek reasons by default: enable_thinking is sent without -t
        (the provider default is resolved into the config at build time)."""
        from janito.llm_clients.api_config import build_api_config

        fake_run = _fake_run_returns("hi")
        config = build_api_config(
            api_type="Completions",
            cli_provider="deepseek",
            cli_model="deepseek-flash",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert fake_run.captured_kwargs["extra_body"]["enable_thinking"] is True

    def test_run_turn_thinking_defaults_on_for_alibaba():
        """Alibaba/Qwen reasons by default: enable_thinking is sent without -t
        (the provider default is resolved into the config at build time)."""
        from janito.llm_clients.api_config import build_api_config

        fake_run = _fake_run_returns("hi")
        config = build_api_config(
            api_type="Completions",
            cli_provider="alibaba",
            cli_model="qwen3.8-max",
            reasoning_effort="xhigh",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert fake_run.captured_kwargs["extra_body"]["enable_thinking"] is True

    def test_run_turn_omits_builtin_tools_for_alibaba_completions():
        """Alibaba's qwen3.8-max has its built-in tools disabled on the
        Completions API (the deployment rejects code_interpreter with a 400),
        so no enable_* tool flags are sent on the CLI Completions path."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="alibaba",
            model="qwen3.8-max",
            reasoning_effort="xhigh",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        extra_body = fake_run.captured_kwargs.get("extra_body", {})
        assert "enable_code_interpreter" not in extra_body
        assert "enable_search" not in extra_body

    def test_run_turn_no_builtin_tools_for_openai():
        """Models without built-in tools send no tool enable flags."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="openai",
            model="gpt-4",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert "enable_code_interpreter" not in fake_run.captured_kwargs.get("extra_body", {})
        assert "enable_search" not in fake_run.captured_kwargs.get("extra_body", {})

    def test_run_turn_thinking_defaults_on_for_minimax():
        """MiniMax-M3 reasons by default: the structured thinking dict is
        passed through (extra_body thinking {'type': 'adaptive'}) without -t
        (the provider default is resolved into the config at build time)."""
        from janito.llm_clients.api_config import build_api_config

        fake_run = _fake_run_returns("hi")
        config = build_api_config(
            api_type="Completions",
            cli_provider="minimax",
            cli_model="MiniMax-M3",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert fake_run.captured_kwargs["extra_body"]["thinking"] == {"type": "adaptive"}

    def test_run_turn_thinking_off_by_default_for_openai():
        """OpenAI has no default thinking: enable_thinking is not sent."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="openai",
            model="gpt-4",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))

        assert "extra_body" not in fake_run.captured_kwargs

    def test_run_turn_explicit_thinking_flag_still_wins():
        """-t forces enable_thinking even for providers without a default (the
        flag is resolved into the config at build time)."""
        from janito.llm_clients.api_config import build_api_config

        fake_run = _fake_run_returns("hi")
        config = build_api_config(
            api_type="Completions",
            cli_provider="openai",
            cli_model="gpt-4",
            thinking=True,
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))
        assert fake_run.captured_kwargs["extra_body"]["enable_thinking"] is True

    def test_run_turn_gemini_flavor_skips_enable_thinking():
        """Gemini-flavored providers (google) never send enable_thinking (the
        field does not exist on their OpenAI-compatibility layer); no
        thinking_config payload is sent either."""
        from janito.llm_clients.api_config import build_api_config

        fake_run = _fake_run_returns("hi")
        config = build_api_config(
            api_type="Completions",
            cli_provider="google",
            cli_model="gemini-3.7-flash",
            reasoning_effort="medium",
            thinking=True,
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))
        extra_body = fake_run.captured_kwargs.get("extra_body")
        # enable_thinking must NOT be sent for Gemini-flavored providers.
        assert not extra_body or "enable_thinking" not in extra_body
        # No thinking_config payload either.
        assert not extra_body or "extra_body" not in extra_body
        # Explicit reasoning_effort is forwarded (default for gemini is medium).
        assert fake_run.captured_kwargs["reasoning_effort"] == "medium"

    def test_run_turn_gemini_flavor_forwards_reasoning_effort():
        """The resolved reasoning level is sent as reasoning_effort for
        Gemini-flavored providers (e.g. --reasoning-effort high)."""
        fake_run = _fake_run_returns("hi")
        config = make_config(
            provider="google",
            model="gemini-3.7-flash",
            reasoning_effort="high",
            use_mcp=False,
        )
        client_mod.run_turn(config, "hello", ui_config=make_ui_config(stream_runner=fake_run))
        assert fake_run.captured_kwargs["reasoning_effort"] == "high"

    def test_build_call_kwargs_forwards_reasoning_effort():
        class _Cfg:
            effective_thinking = False

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("qwen3.8-max", _Cfg(), 1000, None, "xhigh")
        assert kwargs["reasoning_effort"] == "xhigh"
        assert kwargs["model"] == "qwen3.8-max"
        assert kwargs["stream"] is True

    def test_build_call_kwargs_omits_reasoning_effort_when_none():
        class _Cfg:
            effective_thinking = False

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("gpt-4", _Cfg(), 1000, None, None)
        assert "reasoning_effort" not in kwargs

    def test_build_call_kwargs_enables_thinking_when_effective():
        """Web agent sends enable_thinking when the effective state is on
        (runtime toggle, --thinking flag, or provider default)."""

        class _Cfg:
            effective_thinking = True

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("deepseek-flash", _Cfg(), 1000, None, None)
        assert kwargs["extra_body"]["enable_thinking"] is True

    def test_build_call_kwargs_gemini_flavor_skips_enable_thinking():
        """Web agent skips enable_thinking for Gemini-flavored providers
        (google): the field does not exist on Google's OpenAI-compatibility
        layer, and no thinking_config payload is sent."""

        class _Cfg:
            effective_thinking = True
            effective_provider = "google"

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("gemini-3.7-flash", _Cfg(), 1000, None, None)
        extra_body = kwargs.get("extra_body")
        assert not extra_body or "enable_thinking" not in extra_body
        assert not extra_body or "extra_body" not in extra_body
        assert "reasoning_effort" not in kwargs

    def test_build_call_kwargs_gemini_flavor_forwards_reasoning_effort():
        """The web agent forwards the resolved reasoning level as
        reasoning_effort for Gemini-flavored providers."""

        class _Cfg:
            effective_thinking = False
            effective_provider = "google"

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("gemini-3.7-flash", _Cfg(), 1000, None, "medium")
        assert kwargs["reasoning_effort"] == "medium"

    def test_build_call_kwargs_omits_thinking_when_off():
        """Web agent omits enable_thinking when the effective state is off."""

        class _Cfg:
            effective_thinking = False

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("gpt-4", _Cfg(), 1000, None, None)
        assert "extra_body" not in kwargs

    def test_build_call_kwargs_passes_builtin_tools_for_qwen_max():
        """Web agent sends the model's built-in tools as extra_body enable_*
        flags (e.g. Alibaba/Qwen's code_interpreter / web_search /
        web_extractor on the Completions API)."""

        class _Cfg:
            effective_thinking = True

            def effective_tools_for(self, api_type):
                return [
                    {"type": "code_interpreter"},
                    {"type": "web_search"},
                    {"type": "web_extractor"},
                ]

        kwargs = build_call_kwargs("qwen3.8-max", _Cfg(), 1000, None, None)
        # code_interpreter only supports calls in thinking mode, so it also
        # forces enable_thinking on; web_search / web_extractor share
        # enable_search.
        assert kwargs["extra_body"] == {
            "enable_code_interpreter": True,
            "enable_thinking": True,
            "enable_search": True,
        }

    def test_build_call_kwargs_omits_builtin_tools_when_none():
        """Models without built-in tools send no tool enable flags."""

        class _Cfg:
            effective_thinking = False

            def effective_tools_for(self, api_type):
                return None

        kwargs = build_call_kwargs("gpt-4", _Cfg(), 1000, None, None)
        assert "extra_body" not in kwargs

    def test_cli_parser_accepts_reasoning_effort_choices():
        from janito.cli.parser import create_parser

        for level in ("low", "medium", "high", "xhigh", "none", "minimal", "max"):
            args = create_parser().parse_args(["--reasoning-effort", level, "prompt"])
            assert args.reasoning_effort == level

    def test_cli_parser_rejects_invalid_reasoning_effort():
        from janito.cli.parser import create_parser

        with pytest.raises(SystemExit):
            create_parser().parse_args(["--reasoning-effort", "turbo", "prompt"])

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                except TypeError:
                    # Skip tests that require monkeypatch/tmp_path fixtures.
                    continue
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
