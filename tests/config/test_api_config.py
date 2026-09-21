"""
Tests for the resolved per-session API configuration (issue #70).

Covers the ``APIConfig`` dataclass contract and the ``build_api_config``
single resolution point:

- the builder resolves provider / model / endpoint / api_key from the CLI
  args and the auth store (the ``cli_api_type`` selects the built-in default
  endpoint for native-SDK API types, e.g. DashScope);
- token / reasoning fallbacks (config override > built-in default > 100k);
- ``preserve_thinking`` is resolved from the provider config (a built-in
  model default, not a configurable setting);
- the UI config (``UIConfig``) defaults to the headless ``NullObserver`` and
  carries the stream runner + observer (out of ``APIConfig``);
- the dataclass is frozen (mutation raises ``FrozenInstanceError``).
"""

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
from janito.auth_config import set_api_key
from janito.config_store import set_config_value
from janito.llm_adapters.observer import NullObserver
from janito.llm_clients.api_config import APIConfig, build_api_config
from janito.ui.config import UIConfig


@pytest.fixture(autouse=True)
def _isolate_config_dir(monkeypatch, tmp_path):
    """Point the config directory at a temp dir for every test.

    ``build_api_config`` reads the auth store (``~/.janito/auth.json``) and
    the config store (``~/.janito/config.json``), which live in the real
    ``~/.janito`` by default. Without this fixture tests would read/write the
    developer's actual config, making them order- and environment-dependent.
    """
    monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path)
    # A clean auth store per test: the providers used below need an API key.
    for _provider, _key in {
        "alibaba": "sk-test-alibaba",
        "openai": "sk-test-openai",
        "deepseek": "sk-test-deepseek",
        "minimax": "sk-test-minimax",
    }.items():
        set_api_key(_provider, _key)


def _make_observer():
    """Return a minimal TurnObserver implementation for injection tests."""

    class _Observer:
        def on_reasoning(self, content):  # pragma: no cover - protocol stub
            pass

        def on_message(self, content):  # pragma: no cover - protocol stub
            pass

        def on_verbose_info(self, **kwargs):  # pragma: no cover - protocol stub
            pass

        def on_verbose_call(self, call_kwargs, tools_schemas):  # pragma: no cover
            pass

        def on_verbose_response(self, *args, **kwargs):  # pragma: no cover
            pass

        def on_error(self, e, **kwargs):  # pragma: no cover - protocol stub
            pass

        def on_turn_complete(self, token_stats, api_config):  # pragma: no cover - protocol stub
            pass

    return _Observer()


# ---- builder: identity / endpoint / api_key -------------------------------


def test_build_api_config_resolves_cli_args_for_completions():
    """CLI provider/model + auth-store key resolve into the config."""
    config = build_api_config(api_type="Completions", cli_provider="openai", cli_model="gpt-5.6-luna")
    assert config.provider == "openai"
    assert config.api_type == "Completions"
    assert config.model == "gpt-5.6-luna"
    # Standard OpenAI endpoint: base_url stays None.
    assert config.base_url is None
    assert config.api_key == "sk-test-openai"  # pragma: allowlist secret


def test_build_api_config_api_type_selects_native_endpoint():
    """cli_api_type selects the built-in default endpoint per API type.

    Alibaba's ``endpoint_by_api_type`` maps the OpenAI-compatible
    Completions/Responses gateway and the native DashScope SDK URL to
    different base URLs; the resolved api_type must pick the right one.
    """
    responses = build_api_config(api_type="Responses", cli_provider="alibaba", cli_model="qwen3.8-max")
    assert responses.base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    native = build_api_config(api_type="DashScope", cli_provider="alibaba", cli_model="qwen3.8-max")
    assert native.base_url == "https://dashscope-intl.aliyuncs.com/api/v1"
    assert native.api_key == "sk-test-alibaba"  # pragma: allowlist secret


def test_build_api_config_gemini_api_type_selects_native_endpoint():
    """The Gemini API type resolves the native google-genai base URL (the
    OpenAI-compatibility layer URL would be wrong for the native SDK)."""
    for _provider, _key in {
        "alibaba": "sk-test-alibaba",
        "openai": "sk-test-openai",
        "google": "sk-test-google",
    }.items():
        set_api_key(_provider, _key)
    config = build_api_config(api_type="Gemini", cli_provider="google", cli_model="gemini-3.7-flash")
    assert config.base_url == "https://generativelanguage.googleapis.com"
    assert config.api_key == "sk-test-google"  # pragma: allowlist secret


def test_build_api_config_uses_configured_provider_default():
    """Without CLI args the configured provider/model from config.json apply."""
    set_config_value("provider", "alibaba")
    set_config_value("alibaba.model", "qwen3.8-max")
    config = build_api_config(api_type="Responses")
    assert config.provider == "alibaba"
    assert config.model == "qwen3.8-max"


def test_build_api_config_raises_without_provider_or_key():
    """An unresolvable provider/key surfaces as ValueError."""
    with pytest.raises(ValueError):
        build_api_config(api_type="Completions", cli_provider="custom")


# ---- builder: token / reasoning fallbacks --------------------------------


def test_build_api_config_builtin_token_defaults():
    """Built-in provider-config defaults apply when no config override is set."""
    config = build_api_config(api_type="Responses", cli_provider="openai", cli_model="gpt-5.6-luna")
    assert config.max_output_tokens == 128000
    assert config.max_input_tokens == 1050000


def test_build_api_config_config_override_wins_over_builtin():
    """A model-scoped config override beats the built-in default."""
    set_config_value("openai.models.gpt-5.6-luna.max-output-tokens", 4096)
    set_config_value("openai.models.gpt-5.6-luna.reasoning-effort", "low")
    config = build_api_config(api_type="Responses", cli_provider="openai", cli_model="gpt-5.6-luna")
    assert config.max_output_tokens == 4096
    assert config.reasoning_effort == "low"


def test_build_api_config_reasoning_falls_back_to_builtin(monkeypatch):
    """Built-in reasoning default (alibaba medium) applies when not configured."""
    config = build_api_config(api_type="Responses", cli_provider="alibaba", cli_model="qwen3.8-max")
    assert config.reasoning_effort == "medium"
    # CLI --reasoning-effort still wins over the built-in default.
    config = build_api_config(
        api_type="Responses",
        cli_provider="alibaba",
        cli_model="qwen3.8-max",
        reasoning_effort="low",
    )
    assert config.reasoning_effort == "low"


def test_build_api_config_thinking_falls_back_to_builtin():
    """Built-in thinking default (deepseek True) applies when not forced."""
    config = build_api_config(api_type="Responses", cli_provider="deepseek", cli_model="deepseek-flash")
    assert config.thinking is True
    # The explicit --thinking flag wins over the built-in default.
    config = build_api_config(
        api_type="Responses",
        cli_provider="deepseek",
        cli_model="deepseek-flash",
        thinking=True,
    )
    assert config.thinking is True
    # A falsy flag means "not forced on" -> the built-in default applies
    # (preserving the historical CLI semantics: /thinking off does not turn
    # off providers that reason by default).
    config = build_api_config(
        api_type="Responses",
        cli_provider="deepseek",
        cli_model="deepseek-flash",
        thinking=False,
    )
    assert config.thinking is True


def test_build_api_config_thinking_pass_through_dict_default():
    """MiniMax-M3's structured thinking parameter is resolved into the config."""
    config = build_api_config(api_type="Completions", cli_provider="minimax", cli_model="minimax-m3")
    assert config.thinking == {"type": "adaptive"}


def test_build_api_config_output_tokens_falls_back_to_100k():
    """No config override and no built-in default -> 100_000.

    An unregistered provider/model pair has no built-in defaults anywhere in
    the registry, so the fallback chain (config > built-in > 100k) is
    exercised for real.
    """
    set_api_key("unknown-provider", "sk-test-unknown")
    config = build_api_config(
        api_type="Completions",
        cli_provider="unknown-provider",
        cli_model="some-model",
    )
    assert config.max_output_tokens == 100_000
    assert config.max_input_tokens is None
    assert config.reasoning_effort is None


# ---- builder: preserve_thinking / UI injection ----------------------------


def test_build_api_config_resolves_preserve_thinking_from_provider_config():
    """preserve_thinking comes from the provider config's model entry.

    It is no longer a configurable setting: Alibaba/Qwen's hybrid-thinking
    models declare it True (their API appends previous reasoning_content to
    the next input), while models without a built-in declaration resolve to
    None (the caller sends no flag and the API's own default applies).
    """
    # Alibaba/Qwen declare preserve_thinking True.
    config = build_api_config(api_type="Responses", cli_provider="alibaba", cli_model="qwen3.8-max")
    assert config.preserve_thinking is True

    # Models without a built-in declaration resolve to None.
    config = build_api_config(api_type="Completions", cli_provider="openai", cli_model="gpt-5.6-luna")
    assert config.preserve_thinking is None

    # A legacy flat config key no longer has any effect: the value is
    # resolved from the provider config, never from the config store.
    set_config_value("preserve_thinking", True)
    config = build_api_config(api_type="Completions", cli_provider="openai", cli_model="gpt-5.6-luna")
    assert config.preserve_thinking is None


def test_ui_config_defaults_to_headless():
    """The UI config defaults to the headless NullObserver / no runner."""
    ui = UIConfig()
    assert isinstance(ui.observer, NullObserver)
    assert ui.stream_runner is None


def test_ui_config_injects_settings():
    """stream_runner / observer are stored as given."""
    runner = lambda func, *a, **k: func(*a, **k)  # noqa: E731
    observer = _make_observer()
    ui = UIConfig(stream_runner=runner, observer=observer)
    assert ui.stream_runner is runner
    assert ui.observer is observer


def test_api_config_carries_no_ui_fields():
    """UI concerns live in UIConfig, not APIConfig (the split)."""
    config = build_api_config(api_type="Completions", cli_provider="openai", cli_model="gpt-5.6-luna")
    assert config.use_mcp is True
    assert not hasattr(config, "verbose")
    assert not hasattr(config, "stream_runner")
    assert not hasattr(config, "observer")


# ---- dataclass contract ---------------------------------------------------


def test_api_config_is_frozen():
    """APIConfig is immutable: mutation raises FrozenInstanceError."""
    config = build_api_config(api_type="Completions", cli_provider="openai", cli_model="gpt-5.6-luna")
    with pytest.raises(FrozenInstanceError):
        config.model = "other-model"


def test_api_config_constructed_directly():
    """The dataclass can be built directly (used by tests / embeddings)."""
    config = APIConfig(
        provider="openai",
        api_type="Completions",
        model="gpt-5.6-luna",
        base_url=None,
        api_key="sk-test",  # pragma: allowlist secret
        max_output_tokens=100_000,
        max_input_tokens=None,
        reasoning_effort=None,
        thinking=False,
        preserve_thinking=None,
        use_mcp=True,
    )
    assert config.model == "gpt-5.6-luna"
