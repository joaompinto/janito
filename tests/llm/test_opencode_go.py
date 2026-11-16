"""Tests for the OpenCode Go provider (``opencode-go``).

OpenCode Go is a subscription plan on the OpenCode Console gateway.  Its Go
base URL (``https://opencode.ai/inference/go/openai/v1``) is OpenAI-compatible
and translates every Go text model to its native API, so the provider is
Chat-Completions-only and ships a built-in model catalog.

These tests cover:
1. the provider entry (default model, endpoint, model catalog metadata);
2. registry / provider-name resolution;
3. model-name validation against the built-in catalog;
4. runtime resolution (``resolve_runtime_config``) and the default API type;
5. cost estimation, including cache reads and context-tier rates.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
from janito.auth_config import set_api_key
from janito.providers.costing import get_provider_cost, get_provider_cost_value
from janito.providers.registry import get_provider
from janito.providers.validation import (
    canonical_provider_name,
    is_supported_provider,
    list_supported_providers,
    validate_model_name,
)


def _use_temp_config(monkeypatch, tmp_path):
    """Point the config directory at a temporary directory."""
    config_path = tmp_path / ".janito" / "config.json"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
    return config_path


# ---------------------------------------------------------------------------
# 1. Provider entry
# ---------------------------------------------------------------------------


def test_provider_registered():
    assert "opencode-go" in list_supported_providers()
    assert is_supported_provider("opencode-go")


def test_provider_config_shape():
    provider = get_provider("opencode-go")
    assert provider.default_model() == "glm-5.3-flash"
    assert provider.endpoint_for("Completions") == "https://opencode.ai/inference/go/openai/v1"
    assert provider.has_usable_builtin_models() is True
    assert provider.is_custom is False


def test_default_model_metadata():
    provider = get_provider("opencode-go")
    model = provider.model_config()
    assert model.get("supported_api_types") == ["Completions"]
    assert model.get("default_api_type") == "Completions"
    assert model.get("max_input_tokens") == 1_000_000
    assert model.get("max_output_tokens") == 131_072
    efforts = [entry["effort"] for entry in model.get("supported_reasoning_efforts")]
    assert efforts == ["low", "high", "max"]


def test_model_catalog_covers_go_catalog():
    provider = get_provider("opencode-go")
    names = set(provider.model_names())
    # A representative slice across vendors plus the free models.
    assert {
        "claude-haiku-5-5",
        "deepseek-v4.1-flash",
        "gemini-4-argon",
        "glm-5.3-flash",
        "gpt-6-luna",
        "grok-4.7",
        "kimi-k3.1-pro",
        "mimo-v2.6-pro",
        "minimax-m3",
        "muse-spark-1.3-contributor",
        "qwen3.8-max",
        "beam-free",
        "iceman-contributor-free",
        "longcat-2.5-free",
    } <= names
    # Every model entry carries a usable API type and token limits.
    for name in provider.model_names():
        config = provider.model_config(name)
        assert config.get("supported_api_types") == ["Completions"]
        assert config.get("max_input_tokens") > 0
        assert config.get("max_output_tokens") > 0


# ---------------------------------------------------------------------------
# 2. Registry
# ---------------------------------------------------------------------------


def test_registry_resolves_case_insensitively():
    assert canonical_provider_name("opencode-go") == "opencode-go"
    assert canonical_provider_name("OpenCode-Go") == "opencode-go"
    provider = get_provider("OPENCODE-GO")
    assert provider is not None
    assert provider.name == "opencode-go"


def test_provider_is_not_a_variant():
    provider = get_provider("opencode-go")
    assert provider.is_variant is False


# ---------------------------------------------------------------------------
# 3. Model validation
# ---------------------------------------------------------------------------


def test_model_validation_accepts_catalog_models():
    assert validate_model_name("opencode-go", "glm-5.3-flash") == "glm-5.3-flash"
    # Canonical casing comes from the catalog.
    assert validate_model_name("opencode-go", "Glm-5.3-Flash") == "glm-5.3-flash"


def test_model_validation_rejects_unknown_models():
    with pytest.raises(ValueError, match="opencode-go"):
        validate_model_name("opencode-go", "not-a-go-model")


# ---------------------------------------------------------------------------
# 4. Runtime resolution
# ---------------------------------------------------------------------------


def test_resolve_runtime_config_defaults(monkeypatch, tmp_path):
    from janito.runtime_config import resolve_runtime_config

    _use_temp_config(monkeypatch, tmp_path)
    set_api_key("opencode-go", "oc_sk_test")  # pragma: allowlist secret

    base_url, api_key, model = resolve_runtime_config(None, "opencode-go")
    assert base_url == "https://opencode.ai/inference/go/openai/v1"
    assert api_key == "oc_sk_test"  # pragma: allowlist secret
    assert model == "glm-5.3-flash"


def test_resolve_runtime_config_explicit_model(monkeypatch, tmp_path):
    from janito.runtime_config import resolve_runtime_config

    _use_temp_config(monkeypatch, tmp_path)
    set_api_key("opencode-go", "oc_sk_test")  # pragma: allowlist secret

    base_url, _, model = resolve_runtime_config("kimi-k3.1-pro", "opencode-go")
    assert base_url == "https://opencode.ai/inference/go/openai/v1"
    assert model == "kimi-k3.1-pro"


def test_default_api_type_is_completions(monkeypatch, tmp_path):
    from janito.general_config import resolve_api_type

    _use_temp_config(monkeypatch, tmp_path)

    assert resolve_api_type(None, "opencode-go") == "Completions"


# ---------------------------------------------------------------------------
# 5. Cost estimation
# ---------------------------------------------------------------------------


def test_cost_uses_base_rates_and_cache_reads():
    # glm-5.3-flash: $0.15 in / $0.03 cached in / $0.50 out per 1M tokens.
    # 1M input (500K cached) + 1M output = 500K*0.15 + 500K*0.03 + 1M*0.50.
    cost = get_provider_cost_value("opencode-go", "glm-5.3-flash", 1_000_000, 1_000_000, 500_000)
    assert cost == pytest.approx(0.59)


def test_cost_applies_context_tier_to_whole_request():
    # GPT-6 Luna: $0.10/$0.50 below 272K, $0.20/$0.75 above it.
    below = get_provider_cost_value("opencode-go", "gpt-6-luna", 200_000, 10_000, 0)
    above = get_provider_cost_value("opencode-go", "gpt-6-luna", 300_000, 10_000, 0)
    assert below == pytest.approx(0.025)
    assert above == pytest.approx(0.0675)


def test_free_models_cost_nothing():
    assert get_provider_cost_value("opencode-go", "beam-free", 1_000_000, 1_000_000, 0) == 0.0


def test_unknown_model_cost_is_na():
    assert get_provider_cost("opencode-go", "not-a-go-model", 100, 50, 0) == "N/A"
    assert get_provider_cost_value("opencode-go", "not-a-go-model", 100, 50, 0) is None
