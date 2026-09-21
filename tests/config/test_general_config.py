"""
Tests for provider-scoped configuration in general_config.

The ``model`` and ``endpoint`` config keys are stored per-provider under
``providers.<provider>.model`` and ``providers.<provider>.endpoint`` so that each
provider can have its own default model and endpoint. The provider is resolved
from the ``--provider`` CLI argument first, then from the configured ``provider``
value.

Note: Legacy flat keys (e.g. "openai.model") are NOT automatically migrated.
Users with old configs must manually update them to the new nested structure.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_cli as cc
import janito.config_dir as config_dir_mod
import janito.config_keys as ck
import janito.config_loaders as cl
import janito.config_store as cs
import janito.general_config as gc
from janito.config_cli import ProviderRequiredError

try:
    import anthropic  # noqa: F401

    _HAS_ANTHROPIC = True
except ModuleNotFoundError:
    _HAS_ANTHROPIC = False

# The "aborts without the package" guard test only applies when the optional
# `anthropic` package is missing; skip it when it is installed.
requires_no_anthropic = pytest.mark.skipif(
    _HAS_ANTHROPIC, reason="anthropic package is installed (guard not exercised)"
)


def _use_temp_config(monkeypatch, tmp_path):
    """Point the config directory at a temporary directory."""
    config_path = tmp_path / ".janito" / "config.json"
    # The config dir is the single source of truth for all config file paths,
    # so override it to point at the temp directory.
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
    return config_path


def _read_config(config_path):
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return json.load(f)


if pytest is not None:

    def test_set_model_without_provider_errors(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ProviderRequiredError):
            cc.set_config_from_cli("model=gpt-5.6-luna")
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_set_model_with_cli_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        key, value = cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        assert key == "openai.model"
        assert value == "gpt-5.6-luna"
        assert _read_config(config_path) == {"providers": {"openai": {"model": "gpt-5.6-luna"}}}

    def test_set_model_uses_configured_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=minimax")
        key, _ = cc.set_config_from_cli("model=MiniMax-M3")
        assert key == "minimax.model"
        assert _read_config(config_path)["providers"]["minimax"]["model"] == "MiniMax-M3"

    def test_cli_provider_overrides_configured_provider(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=minimax")
        key, _ = cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        assert key == "openai.model"

    def test_provider_is_normalized(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        key, _ = cc.set_config_from_cli("model=gpt-5.6-luna", "  OpenAI ")
        assert key == "openai.model"

    def test_set_model_rejects_unknown_model(monkeypatch, tmp_path):
        """--set model=<unknown> is rejected for providers with built-in models."""
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError, match="Unknown model 'gpt-4'"):
            cc.set_config_from_cli("model=gpt-4", "openai")
        # Nothing should have been written.
        assert _read_config(config_path) == {}

    def test_set_model_error_lists_available_models(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as excinfo:
            cc.set_config_from_cli("model=nope", "deepseek")
        message = str(excinfo.value)
        assert "for provider 'deepseek'" in message
        assert "deepseek-flash" in message
        assert "deepseek-v4-pro" in message

    def test_set_model_canonicalizes_builtin_casing(monkeypatch, tmp_path):
        """A case-insensitive match is stored in its canonical built-in casing."""
        config_path = _use_temp_config(monkeypatch, tmp_path)
        key, value = cc.set_config_from_cli("model=MINIMAX-M3", "minimax")
        assert key == "minimax.model"
        assert value == "MiniMax-M3"
        assert _read_config(config_path)["providers"]["minimax"]["model"] == "MiniMax-M3"

    def test_set_model_accepts_any_name_for_custom_and_openrouter(monkeypatch, tmp_path):
        """custom and openrouter have no built-in model list: any name is accepted."""
        _use_temp_config(monkeypatch, tmp_path)
        key, value = cc.set_config_from_cli("model=my-arbitrary-model", "custom")
        assert key == "custom.model"
        assert value == "my-arbitrary-model"
        key, value = cc.set_config_from_cli("model=anthropic/claude-3.5-sonnet", "openrouter")
        assert key == "openrouter.model"
        assert value == "anthropic/claude-3.5-sonnet"

    def test_set_model_accepts_configured_per_model_entry(monkeypatch, tmp_path):
        """A model with per-model config entries (shown by --list-models) is accepted."""
        _use_temp_config(monkeypatch, tmp_path)
        cs.set_config_value("openai.models.gpt-future.max-output-tokens", 1000)
        key, value = cc.set_config_from_cli("model=gpt-future", "openai")
        assert key == "openai.model"
        assert value == "gpt-future"

    def test_get_model_per_provider(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        cc.set_config_from_cli("model=MiniMax-M3", "minimax")
        assert cc.get_config_from_cli("model", "openai") == "gpt-5.6-luna"
        assert cc.get_config_from_cli("model", "minimax") == "MiniMax-M3"

    def test_get_model_without_provider_errors(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        # A config file must exist for --get; write an unrelated (non-scoped) key.
        cs.set_config_value("theme", "dark")
        with pytest.raises(ProviderRequiredError):
            cc.get_config_from_cli("model")
        assert config_path.exists()

    def test_load_model_from_config(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=minimax")
        cc.set_config_from_cli("model=MiniMax-M3")
        cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        # Active provider (from config) is minimax
        assert cl.load_model_from_config() == "MiniMax-M3"
        # CLI provider override wins
        assert cl.load_model_from_config("openai") == "gpt-5.6-luna"
        # Unknown provider has no model
        assert cl.load_model_from_config("unknown") is None

    def test_load_model_without_provider_returns_none(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        # No provider configured and none supplied -> cannot resolve -> None
        assert cl.load_model_from_config() is None

    def test_unset_model_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        cc.set_config_from_cli("model=MiniMax-M3", "minimax")
        assert cc.unset_config_key_from_cli("model", "openai") is True
        config = _read_config(config_path)
        assert "openai" not in config.get("providers", {})
        assert config["providers"]["minimax"]["model"] == "MiniMax-M3"
        # Removing again returns False (already gone)
        assert cc.unset_config_key_from_cli("model", "openai") is False

    def test_unset_model_without_provider_errors(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("model=gpt-5.6-luna", "openai")
        with pytest.raises(ProviderRequiredError):
            cc.unset_config_key_from_cli("model")

    def test_non_scoped_keys_unaffected(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        key, _ = cc.set_config_from_cli("provider=openai")
        assert key == "provider"
        assert cc.get_config_from_cli("provider") == "openai"
        assert cc.unset_config_key_from_cli("provider") is True
        assert _read_config(config_path) == {}

    def test_set_endpoint_without_provider_errors(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ProviderRequiredError):
            cc.set_config_from_cli("endpoint=http://x/v1")
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_set_endpoint_with_cli_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        key, value = cc.set_config_from_cli("endpoint=http://x/v1", "custom")
        assert key == "custom.endpoint"
        assert value == "http://x/v1"
        assert _read_config(config_path) == {"providers": {"custom": {"endpoint": "http://x/v1"}}}

    def test_set_endpoint_uses_configured_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=custom")
        key, _ = cc.set_config_from_cli("endpoint=http://x/v1")
        assert key == "custom.endpoint"
        assert _read_config(config_path)["providers"]["custom"]["endpoint"] == "http://x/v1"

    def test_get_endpoint_per_provider(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("endpoint=http://a/v1", "custom")
        cc.set_config_from_cli("endpoint=http://b/v1", "openai")
        assert cc.get_config_from_cli("endpoint", "custom") == "http://a/v1"
        assert cc.get_config_from_cli("endpoint", "openai") == "http://b/v1"

    def test_load_endpoint_from_config_per_provider(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=custom")
        cc.set_config_from_cli("endpoint=http://a/v1", "custom")
        cc.set_config_from_cli("endpoint=http://b/v1", "openai")
        # Active provider (from config) is custom
        assert cl.load_endpoint_from_config() == "http://a/v1"
        # CLI provider override wins
        assert cl.load_endpoint_from_config("openai") == "http://b/v1"
        # Unknown provider has no endpoint (and no legacy top-level value)
        assert cl.load_endpoint_from_config("unknown") is None

    def test_load_endpoint_top_level_key_ignored(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        # A top-level 'endpoint' key is ignored (no backward compatibility).
        cs.set_config_value("endpoint", "http://legacy/v1")
        assert cl.load_endpoint_from_config("custom") is None

    def test_unset_endpoint_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("endpoint=http://a/v1", "custom")
        cc.set_config_from_cli("endpoint=http://b/v1", "openai")
        assert cc.unset_config_key_from_cli("endpoint", "custom") is True
        config = _read_config(config_path)
        assert "custom" not in config.get("providers", {})
        assert config["providers"]["openai"]["endpoint"] == "http://b/v1"
        # Removing again returns False (already gone)
        assert cc.unset_config_key_from_cli("endpoint", "custom") is False

    def test_endpoint_config_key_helper():
        assert ck.endpoint_config_key("custom") == "custom.endpoint"
        assert ck.endpoint_config_key("  Custom ") == "custom.endpoint"

    def test_model_config_key_helper():
        assert ck.model_config_key("openai") == "openai.model"
        assert ck.model_config_key("  MiniMax ") == "minimax.model"

    def test_set_max_output_tokens_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=openai")
        cc.set_config_from_cli("max-output-tokens=8192")
        cc.set_config_from_cli("max-output-tokens=4096", "minimax")
        # Each provider/model pair has its own max-output-tokens (resolved to
        # the provider's built-in default model when none is configured).
        assert cl.load_max_output_tokens("openai") == 8192
        assert cl.load_max_output_tokens("minimax") == 4096
        # Verify storage structure (model-scoped path).
        config = _read_config(config_path)
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["max-output-tokens"] == 8192
        assert config["providers"]["minimax"]["models"]["MiniMax-M3"]["max-output-tokens"] == 4096

    def test_unset_max_output_tokens_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("max-output-tokens=8192", "openai")
        cc.set_config_from_cli("max-output-tokens=4096", "minimax")
        assert cc.unset_config_key_from_cli("max-output-tokens", "openai") is True
        config = _read_config(config_path)
        assert "openai" not in config.get("providers", {})
        assert config["providers"]["minimax"]["models"]["MiniMax-M3"]["max-output-tokens"] == 4096
        # Removing again returns False (already gone)
        assert cc.unset_config_key_from_cli("max-output-tokens", "openai") is False

    def test_max_input_tokens_config_key_helper():
        assert (
            ck.model_scoped_config_key("openai", "gpt-5.6-luna", "max-input-tokens")
            == "openai.models.gpt-5.6-luna.max-input-tokens"
        )
        assert (
            ck.model_scoped_config_key("  OpenAI ", "gpt-5.6-luna", "max-input-tokens")
            == "openai.models.gpt-5.6-luna.max-input-tokens"
        )

    def test_set_max_input_tokens_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=openai")
        cc.set_config_from_cli("max-input-tokens=128000")
        cc.set_config_from_cli("max-input-tokens=256000", "minimax")
        # Each provider/model pair has its own max-input-tokens.
        assert cl.load_max_input_tokens("openai") == 128000
        assert cl.load_max_input_tokens("minimax") == 256000
        # Values are stored as ints (coerced via INT_VALUED_KEYS), and the
        # returned key is the model-scoped path.
        key, value = cc.set_config_from_cli("max-input-tokens=200000", "deepseek")
        assert key == "deepseek.models.deepseek-flash.max-input-tokens"
        assert value == 200000
        config = _read_config(config_path)
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["max-input-tokens"] == 128000
        assert config["providers"]["minimax"]["models"]["MiniMax-M3"]["max-input-tokens"] == 256000
        assert config["providers"]["deepseek"]["models"]["deepseek-flash"]["max-input-tokens"] == 200000

    def test_set_max_input_tokens_rejects_non_int(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as exc:
            cc.set_config_from_cli("max-input-tokens=one-hundred-thousand", "openai")
        assert "integer" in str(exc.value)
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_unset_max_input_tokens_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("max-input-tokens=128000", "openai")
        cc.set_config_from_cli("max-input-tokens=256000", "minimax")
        assert cc.unset_config_key_from_cli("max-input-tokens", "openai") is True
        config = _read_config(config_path)
        assert "openai" not in config.get("providers", {})
        assert config["providers"]["minimax"]["models"]["MiniMax-M3"]["max-input-tokens"] == 256000
        # Removing again returns False (already gone)
        assert cc.unset_config_key_from_cli("max-input-tokens", "openai") is False

    def test_set_effort_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=alibaba")
        # Reasoning-effort is model-scoped, so scope the value to the model
        # explicitly (both Qwen models declare reasoning levels; the
        # configured value is stored under qwen3.8-max).
        cc.set_config_from_cli("model=qwen3.8-max", "alibaba")
        cc.set_config_from_cli("effort=xhigh", "alibaba")
        cc.set_config_from_cli("effort=low", "openai")
        # Each provider/model pair has its own effort.
        assert cl.load_effort("alibaba") == "xhigh"
        assert cl.load_effort("openai") == "low"
        # Verify storage structure (model-scoped path).
        config = _read_config(config_path)
        assert config["providers"]["alibaba"]["models"]["qwen3.8-max"]["effort"] == "xhigh"
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["effort"] == "low"
        # Model-scoped set/get round-trips through the CLI helpers.
        assert cc.get_config_from_cli("effort", "alibaba") == "xhigh"

    def test_set_effort_without_provider_errors(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ProviderRequiredError):
            cc.set_config_from_cli("effort=medium")
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_model_scoped_roundtrip_with_explicit_model(monkeypatch, tmp_path):
        """Model-scoped keys round-trip through set/get/unset when an
        explicit --model is given (stored under providers.<p>.models.<m>.<k>)."""
        config_path = _use_temp_config(monkeypatch, tmp_path)
        key, value = cc.set_config_from_cli("max-output-tokens=64000", "openai", "my-model")
        assert key == "openai.models.my-model.max-output-tokens"
        assert value == 64000
        # Reading with the same explicit model returns the stored value.
        assert cc.get_config_from_cli("max-output-tokens", "openai", "my-model") == "64000"
        # A different model for the same provider has no value.
        assert cl.load_max_output_tokens("openai", "other-model") is None
        # Unset removes the model-scoped key (and prunes the emptied dicts).
        assert cc.unset_config_key_from_cli("max-output-tokens", "openai", "my-model") is True
        assert _read_config(config_path) == {}

    def test_model_scoped_unknown_model_uses_default_model_key(monkeypatch, tmp_path):
        """Setting a model-scoped key without --model resolves to the
        provider's configured/default model; an unknown provider raises
        ModelRequiredError when no model can be resolved."""
        config_path = _use_temp_config(monkeypatch, tmp_path)
        # With no configured model, openai's built-in default (gpt-5.6-luna)
        # is used as the target model.
        key, _ = cc.set_config_from_cli("max-output-tokens=32000", "openai")
        assert key == "openai.models.gpt-5.6-luna.max-output-tokens"
        assert _read_config(config_path)["providers"]["openai"]["models"]["gpt-5.6-luna"]["max-output-tokens"] == 32000
        # The custom provider has no default model -> ModelRequiredError.
        from janito.config_cli import ModelRequiredError

        with pytest.raises(ModelRequiredError):
            cc.set_config_from_cli("max-output-tokens=10000", "custom")

    def test_load_effort_unknown_provider_returns_none(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("effort=medium", "alibaba")
        # No provider configured and unknown provider -> None
        assert cl.load_effort("unknown") is None
        assert cl.load_effort() is None

    def test_unset_effort_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("effort=xhigh", "alibaba")
        cc.set_config_from_cli("effort=low", "openai")
        assert cc.unset_config_key_from_cli("effort", "alibaba") is True
        config = _read_config(config_path)
        assert "alibaba" not in config.get("providers", {})
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["effort"] == "low"
        # Removing again returns False (already gone)
        assert cc.unset_config_key_from_cli("effort", "alibaba") is False

    def test_load_max_output_tokens_legacy_keys_ignored(monkeypatch, tmp_path):
        """Legacy provider-scoped context-window-size / underscore-variant
        keys are NO LONGER read (no backward compatibility, see D3)."""
        config_path = _use_temp_config(monkeypatch, tmp_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "openai": {"context-window-size": 65536},
                        "minimax": {"context_window_size": 4096},
                    }
                }
            )
        )
        # Stale legacy keys are ignored: the model-scoped path is empty so
        # the loaders return None.
        assert cl.load_max_output_tokens("openai") is None
        assert cl.load_max_output_tokens("minimax") is None

    def test_determine_provider_priority(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("provider=minimax")
        # CLI provider takes priority over configured provider
        assert gc.determine_provider("openai") == "openai"
        # Falls back to configured provider
        assert gc.determine_provider() == "minimax"
        # No provider anywhere
        cs.unset_config_value("provider")
        assert gc.determine_provider() is None

    # ---- API type (Responses / Completions) ------------------------------

    def test_api_type_config_key_helper():
        assert ck.model_scoped_config_key("openai", "gpt-5.6-luna", "api-type") == "openai.models.gpt-5.6-luna.api-type"
        assert (
            ck.model_scoped_config_key("  OpenAI ", "gpt-5.6-luna", "api-type") == "openai.models.gpt-5.6-luna.api-type"
        )

    def test_set_api_type_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("api-type=Responses", "openai")
        cc.set_config_from_cli("api-type=Completions", "minimax")
        assert cl.load_api_type("openai") == "Responses"
        assert cl.load_api_type("minimax") == "Completions"
        config = _read_config(config_path)
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["api-type"] == "Responses"
        assert config["providers"]["minimax"]["models"]["MiniMax-M3"]["api-type"] == "Completions"

    def test_set_api_type_normalizes_case(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        # Lowercase values (as in `--set api-type=completions`) are normalized
        # to the canonical casing when stored.
        key, value = cc.set_config_from_cli("api-type=completions", "openai")
        assert key == "openai.models.gpt-5.6-luna.api-type"
        assert value == "Completions"
        cc.set_config_from_cli("api-type=responses", "minimax")
        cc.set_config_from_cli("api-type=RESPONSES", "deepseek")
        config = _read_config(config_path)
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["api-type"] == "Completions"
        assert config["providers"]["minimax"]["models"]["MiniMax-M3"]["api-type"] == "Responses"
        assert config["providers"]["deepseek"]["models"]["deepseek-flash"]["api-type"] == "Responses"
        assert cl.load_api_type("openai") == "Completions"
        assert cl.load_api_type("minimax") == "Responses"

    def test_set_api_type_rejects_unknown_values(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as exc:
            cc.set_config_from_cli("api-type=bogus", "openai")
        assert "Unsupported API type" in str(exc.value)
        assert "Responses" in str(exc.value)
        assert "Completions" in str(exc.value)
        assert "Anthropic" in str(exc.value)
        # Nothing should have been written
        assert _read_config(config_path) == {}

    @requires_no_anthropic
    def test_set_api_type_anthropic_aborts_without_package(monkeypatch, tmp_path):
        """Setting the native Anthropic SDK API type without the optional
        `anthropic` package aborts the change (nothing is written) with a
        message naming the package."""
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as exc:
            cc.set_config_from_cli("api-type=Anthropic", "anthropic")
        message = str(exc.value)
        assert "Anthropic" in message
        assert "anthropic" in message
        assert "pip install anthropic" in message
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_set_api_type_dashscope_aborts_without_package(monkeypatch, tmp_path):
        """Setting the native DashScope SDK API type without the optional
        `dashscope` package aborts the change (nothing is written) with a
        message naming the package."""
        import importlib.util

        # Simulate a test environment without the optional package so the
        # guard is exercised even when `dashscope` is installed locally.
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as exc:
            cc.set_config_from_cli("api-type=dashscope", "alibaba")
        message = str(exc.value)
        assert "DashScope" in message
        assert "dashscope" in message
        assert "pip install dashscope" in message
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_set_api_type_gemini_aborts_without_package(monkeypatch, tmp_path):
        """Setting the native Gemini SDK API type without the optional
        `google-genai` package aborts the change (nothing is written) with a
        message naming the package."""
        import importlib.util

        # Simulate a test environment without the optional package so the
        # guard is exercised even when `google-genai` is installed locally.
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as exc:
            cc.set_config_from_cli("api-type=gemini", "google")
        message = str(exc.value)
        assert "Gemini" in message
        assert "google-genai" in message
        assert "pip install google-genai" in message
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_normalize_api_type_accepts_native_sdk_types():
        assert ck.normalize_api_type("anthropic") == "Anthropic"
        assert ck.normalize_api_type("ANTHROPIC") == "Anthropic"
        assert ck.normalize_api_type("Anthropic") == "Anthropic"
        # "DashScope" keeps its canonical casing (capitalize() would mangle it
        # into "Dashscope", so matching is case-insensitive over the known set).
        assert ck.normalize_api_type("dashscope") == "DashScope"
        assert ck.normalize_api_type("DASHSCOPE") == "DashScope"
        assert ck.normalize_api_type("DashScope") == "DashScope"
        # "Gemini" keeps its canonical casing too.
        assert ck.normalize_api_type("gemini") == "Gemini"
        assert ck.normalize_api_type("GEMINI") == "Gemini"
        assert ck.normalize_api_type("Gemini") == "Gemini"

    def test_load_api_type_unknown_provider_returns_none(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("api-type=Responses", "openai")
        assert cl.load_api_type("unknown") is None
        assert cl.load_api_type() is None

    def test_unset_api_type_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("api-type=Responses", "openai")
        assert cc.unset_config_key_from_cli("api-type", "openai") is True
        assert "openai" not in config_path.read_text()
        assert cc.unset_config_key_from_cli("api-type", "openai") is False

    def test_resolve_api_type_defaults_to_provider_default_api_type(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        # OpenAI's model declares default_api_type "Responses" (the first of
        # its supported_api_types), so the default is the Responses API.
        assert gc.resolve_api_type(None, "openai") == "Responses"
        # DeepSeek now ships Responses first too, so it resolves to Responses.
        assert gc.resolve_api_type(None, "deepseek") == "Responses"
        # Alibaba's default model qwen3.8-flash declares Responses as its
        # built-in default API type too.
        assert gc.resolve_api_type(None, "alibaba") == "Responses"
        # Explicit CLI flag wins over the provider default.
        assert gc.resolve_api_type("Completions", "openai") == "Completions"
        assert gc.resolve_api_type("Responses", "deepseek") == "Responses"
        # Case is normalized.
        assert gc.resolve_api_type("responses", "deepseek") == "Responses"
        # The native DashScope SDK type resolves (canonical casing) for alibaba.
        assert gc.resolve_api_type("dashscope", "alibaba") == "DashScope"

    def test_resolve_api_type_from_config(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        # No config: provider default applies (Responses for OpenAI).
        assert gc.resolve_api_type(None, "openai") == "Responses"
        # A per-provider config override wins over the built-in default.
        cc.set_config_from_cli("api-type=Completions", "openai")
        assert gc.resolve_api_type(None, "openai") == "Completions"
        # ... and the CLI flag still wins over the config value.
        assert gc.resolve_api_type("Responses", "openai") == "Responses"

    def test_resolve_api_type_rejects_unknown_values():
        with pytest.raises(ValueError) as exc:
            gc.resolve_api_type("Bogus", "openai")
        assert "Unsupported API type" in str(exc.value)
        assert "Responses" in str(exc.value)
        assert "Completions" in str(exc.value)
        assert "Anthropic" in str(exc.value)

    def test_resolve_api_type_unknown_provider_falls_back_to_completions():
        # An unknown provider has no supported_api_types entry, so the safe
        # Completions default applies.
        assert gc.resolve_api_type(None, "bogus") == "Completions"

    # ---- Responses-in-server (per-provider override) --------------------

    def test_stateless_mode_config_key_helper():
        assert (
            ck.model_scoped_config_key("openai", "gpt-5.6-luna", "stateless-mode")
            == "openai.models.gpt-5.6-luna.stateless-mode"
        )
        assert (
            ck.model_scoped_config_key("  OpenAI ", "gpt-5.6-luna", "stateless-mode")
            == "openai.models.gpt-5.6-luna.stateless-mode"
        )

    def test_set_stateless_mode_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("stateless-mode=true", "openai")
        cc.set_config_from_cli("stateless-mode=false", "deepseek")
        assert cl.load_stateless_mode_from_config("openai") is True
        assert cl.load_stateless_mode_from_config("deepseek") is False
        config = _read_config(config_path)
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["stateless-mode"] is True
        assert config["providers"]["deepseek"]["models"]["deepseek-flash"]["stateless-mode"] is False

    def test_set_stateless_mode_normalizes_bool_forms(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        # 1/0 and on/off (in any case) are normalized to real booleans.
        key, value = cc.set_config_from_cli("stateless-mode=1", "openai")
        assert key == "openai.models.gpt-5.6-luna.stateless-mode"
        assert value is True
        cc.set_config_from_cli("stateless-mode=OFF", "deepseek")
        config = _read_config(config_path)
        assert config["providers"]["openai"]["models"]["gpt-5.6-luna"]["stateless-mode"] is True
        assert config["providers"]["deepseek"]["models"]["deepseek-flash"]["stateless-mode"] is False

    def test_set_stateless_mode_rejects_unknown_values(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        with pytest.raises(ValueError) as exc:
            cc.set_config_from_cli("stateless-mode=maybe", "openai")
        assert "boolean" in str(exc.value)
        # Nothing should have been written
        assert _read_config(config_path) == {}

    def test_load_stateless_mode_defaults_to_none(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        assert cl.load_stateless_mode_from_config("openai") is None
        assert cl.load_stateless_mode_from_config() is None

    def test_unset_stateless_mode_per_provider(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        cc.set_config_from_cli("stateless-mode=true", "openai")
        assert cc.unset_config_key_from_cli("stateless-mode", "openai") is True
        assert "openai" not in config_path.read_text()
        assert cc.unset_config_key_from_cli("stateless-mode", "openai") is False

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        import tempfile

        class _MP:
            def setattr(self, obj, name, value):
                setattr(obj, name, value)

        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                with tempfile.TemporaryDirectory() as d:
                    fn(_MP(), Path(d))
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
